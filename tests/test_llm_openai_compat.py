"""Testes do adaptador ``openai_compat`` com transporte simulado: nenhuma chamada de rede (ADR 0016).

O SDK ``openai`` 3.x usa o ``httpx2`` por baixo (um fork do ``httpx``, mesma API), por isso o
``MockTransport`` vem de lá: o SDK recusa um ``httpx.Client`` comum.
"""

import json

import httpx2
import openai
import pytest
from pydantic import SecretStr

from app.adapters.llm.factory import MISSING_KEY_MESSAGE, MissingKeyLLM, build_llm_client
from app.adapters.llm.fake import FakeLLM
from app.adapters.llm.openai_compat import OpenAICompatClient
from app.config import Settings
from app.domain.errors import RATE_LIMIT_MESSAGE, LLMRateLimited, LLMUnavailable
from app.domain.models import Diagnosis
from app.ports.llm import ChatMessage, LLMParams, ReasoningMode, StructuredMode

CHAVE = "sk-or-v1-chave-que-nunca-deve-vazar-123456"
MENSAGENS: list[ChatMessage] = [
    {"role": "system", "content": "Você é um analista."},
    {"role": "user", "content": "<ticket>SMS não chega</ticket>"},
]
JSON_OK = {"campo": "valor"}


def _params(modo: StructuredMode = "json_schema") -> LLMParams:
    return LLMParams(model="vendor/modelo:free", temperature=0.1, max_tokens=500, structured_mode=modo)


def _resposta(content: str | None = '{"campo": "valor"}', model: str = "vendor/modelo-efetivo", **extra) -> dict:
    corpo = {
        "id": "gen-1", "object": "chat.completion", "created": 1, "model": model,
        "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
    }
    corpo.update(extra)
    return corpo


class Servidor:
    """Transporte simulado: entrega as respostas em sequência e guarda as requisições recebidas."""

    def __init__(self, *respostas: httpx2.Response | Exception) -> None:
        self._respostas = list(respostas)
        self.requisicoes: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        # Grava a requisição recebida e retorna (ou lança) a resposta simulada da fila.
        self.requisicoes.append(request)
        item = self._respostas.pop(0) if len(self._respostas) > 1 else self._respostas[0]
        if isinstance(item, Exception):
            raise item
        return item

    def corpo(self, indice: int = 0) -> dict:
        return json.loads(self.requisicoes[indice].content)


def _cliente(servidor: Servidor, max_retries: int = 0) -> OpenAICompatClient:
    # Instancia o cliente real apontando para o MockTransport em memória do httpx2.
    return OpenAICompatClient(
        api_key=CHAVE, base_url="https://provedor.teste/api/v1", timeout_s=5, max_retries=max_retries,
        http_client=openai.DefaultHttpxClient(transport=httpx2.MockTransport(servidor)),
    )


def _ok(**kw) -> httpx2.Response:
    return httpx2.Response(200, json=_resposta(**kw))


def test_sucesso_devolve_texto_json_uso_latencia_e_modelo_efetivo() -> None:
    servidor = Servidor(_ok())
    r = _cliente(servidor).complete(MENSAGENS, Diagnosis, _params())
    assert r.parsed == JSON_OK
    assert r.text == '{"campo": "valor"}'
    assert r.usage == {"prompt_tokens": 11, "completion_tokens": 7}
    assert r.model_used == "vendor/modelo-efetivo"  # o efetivo, não o pedido
    assert r.latency_ms >= 0
    req = servidor.requisicoes[0]
    assert req.url == "https://provedor.teste/api/v1/chat/completions"
    assert req.headers["authorization"] == f"Bearer {CHAVE}"


def test_tokens_de_raciocinio_entram_no_uso_quando_informados() -> None:
    uso = {"prompt_tokens": 5, "completion_tokens": 50, "total_tokens": 55,
           "completion_tokens_details": {"reasoning_tokens": 40}}
    r = _cliente(Servidor(_ok(usage=uso))).complete(MENSAGENS, Diagnosis, _params())
    assert r.usage == {"prompt_tokens": 5, "completion_tokens": 50, "reasoning_tokens": 40}


def test_resposta_cortada_sem_json_e_devolvida_com_a_razao_o_provedor_e_o_gasto() -> None:
    """O adaptador não decide sobre o corte (ADR 0042): devolve ``finish_reason``, o provedor que atendeu, o id da
    geração e o uso, e o serviço registra tudo antes de falhar."""
    corpo = _resposta(content="", usage={"prompt_tokens": 5, "completion_tokens": 2400, "total_tokens": 2405,
                                          "completion_tokens_details": {"reasoning_tokens": 2077}},
                      provider="ProvedorX")
    corpo["choices"][0]["finish_reason"] = "length"
    r = _cliente(Servidor(httpx2.Response(200, json=corpo))).complete(MENSAGENS, Diagnosis, _params())
    assert r.parsed is None and r.finish_reason == "length"
    assert r.provider_used == "ProvedorX" and r.response_id == "gen-1"
    assert r.usage == {"prompt_tokens": 5, "completion_tokens": 2400, "reasoning_tokens": 2077}


def test_provedor_ausente_vira_texto_vazio() -> None:
    r = _cliente(Servidor(_ok())).complete(MENSAGENS, Diagnosis, _params())
    assert r.provider_used == "" and r.finish_reason == "stop"


def test_corte_por_max_tokens_com_json_completo_e_aceito() -> None:
    corpo = _resposta()
    corpo["choices"][0]["finish_reason"] = "length"
    r = _cliente(Servidor(httpx2.Response(200, json=corpo))).complete(MENSAGENS, Diagnosis, _params())
    assert r.parsed == JSON_OK


def test_modo_json_schema_envia_response_format_estrito() -> None:
    servidor = Servidor(_ok())
    _cliente(servidor).complete(MENSAGENS, Diagnosis, _params("json_schema"))
    corpo = servidor.corpo()
    assert corpo["model"] == "vendor/modelo:free"
    assert corpo["temperature"] == 0.1 and corpo["max_tokens"] == 500
    formato = corpo["response_format"]
    assert formato["type"] == "json_schema"
    assert formato["json_schema"]["strict"] is True
    assert formato["json_schema"]["name"] == "Diagnosis"
    assert formato["json_schema"]["schema"]["additionalProperties"] is False
    assert corpo["messages"] == MENSAGENS  # sem instrução extra: o provedor impõe o schema


def test_modo_json_object_pede_json_e_poe_o_schema_no_prompt_de_sistema() -> None:
    servidor = Servidor(_ok())
    _cliente(servidor).complete(MENSAGENS, Diagnosis, _params("json_object"))
    corpo = servidor.corpo()
    assert corpo["response_format"] == {"type": "json_object"}
    assert corpo["messages"][0]["content"].startswith("Você é um analista.")
    assert "JSON Schema" in corpo["messages"][0]["content"] and "hypotheses" in corpo["messages"][0]["content"]
    assert corpo["messages"][1] == MENSAGENS[1]
    assert MENSAGENS[0]["content"] == "Você é um analista."  # a entrada não é mutada


def test_modo_prompt_nao_envia_response_format() -> None:
    servidor = Servidor(_ok())
    _cliente(servidor).complete(MENSAGENS, Diagnosis, _params("prompt"))
    corpo = servidor.corpo()
    assert "response_format" not in corpo
    assert "hypotheses" in corpo["messages"][0]["content"]


def test_modo_prompt_sem_mensagem_de_sistema_cria_uma() -> None:
    servidor = Servidor(_ok())
    _cliente(servidor).complete(MENSAGENS[1:], Diagnosis, _params("prompt"))
    primeira = servidor.corpo()["messages"][0]
    assert primeira["role"] == "system" and "JSON Schema" in primeira["content"]


def test_json_dentro_de_cerca_de_codigo_e_extraido() -> None:
    r = _cliente(Servidor(_ok(content='```json\n{"campo": "valor"}\n```'))).complete(MENSAGENS, Diagnosis, _params())
    assert r.parsed == JSON_OK


def test_texto_sem_json_nao_e_erro_do_adaptador() -> None:
    """Resposta inválida volta com ``parsed=None``: quem decide o reparo é o serviço."""
    r = _cliente(Servidor(_ok(content="Desculpe, não consigo."))).complete(MENSAGENS, Diagnosis, _params())
    assert r.parsed is None and r.text == "Desculpe, não consigo."


def test_conteudo_nulo_vira_texto_vazio() -> None:
    r = _cliente(Servidor(_ok(content=None))).complete(MENSAGENS, Diagnosis, _params())
    assert r.text == "" and r.parsed is None


def test_429_vira_llm_rate_limited_com_mensagem_amigavel(caplog) -> None:
    servidor = Servidor(httpx2.Response(429, json={"error": {"message": "Rate limit exceeded"}}))
    with caplog.at_level("WARNING", logger="fellowsupport.llm"), pytest.raises(LLMRateLimited) as exc:
        _cliente(servidor).complete(MENSAGENS, Diagnosis, _params())
    assert str(exc.value) == RATE_LIMIT_MESSAGE == "Limite do modelo gratuito atingido; tente em instantes."
    assert "Rate limit exceeded" not in str(exc.value)  # o texto cru do provedor não chega ao usuário...
    assert "Rate limit exceeded" in caplog.text  # ...mas fica no log para diagnóstico


def test_429_e_repetido_pelo_sdk_e_depois_tem_sucesso() -> None:
    espera_curta = {"retry-after-ms": "1"}
    servidor = Servidor(httpx2.Response(429, json={"error": {"message": "x"}}, headers=espera_curta), _ok())
    r = _cliente(servidor, max_retries=1).complete(MENSAGENS, Diagnosis, _params())
    assert r.parsed == JSON_OK
    assert len(servidor.requisicoes) == 2


def test_5xx_esgota_as_tentativas_e_vira_llm_unavailable() -> None:
    fora_do_ar = httpx2.Response(503, json={"error": {"message": "fora do ar"}}, headers={"retry-after-ms": "1"})
    servidor = Servidor(fora_do_ar)
    with pytest.raises(LLMUnavailable, match="503"):
        _cliente(servidor, max_retries=2).complete(MENSAGENS, Diagnosis, _params())
    assert len(servidor.requisicoes) == 3  # 1 tentativa + 2 repetições


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_erros_de_cliente_viram_llm_unavailable_sem_repetir(status: int) -> None:
    servidor = Servidor(httpx2.Response(status, json={"error": {"message": "recusado"}}))
    with pytest.raises(LLMUnavailable, match=str(status)):
        _cliente(servidor, max_retries=2).complete(MENSAGENS, Diagnosis, _params())
    assert len(servidor.requisicoes) == 1


def test_timeout_vira_llm_unavailable() -> None:
    servidor = Servidor(httpx2.ReadTimeout("lento"))
    with pytest.raises(LLMUnavailable, match="timeout"):
        _cliente(servidor).complete(MENSAGENS, Diagnosis, _params())


def test_falha_de_conexao_vira_llm_unavailable() -> None:
    servidor = Servidor(httpx2.ConnectError("sem rede"))
    with pytest.raises(LLMUnavailable, match="conectar"):
        _cliente(servidor).complete(MENSAGENS, Diagnosis, _params())


def test_resposta_200_com_erro_no_corpo() -> None:
    corpo_erro = httpx2.Response(200, json={"error": {"message": "modelo caiu", "code": 502}})
    with pytest.raises(LLMUnavailable, match="modelo caiu"):
        _cliente(Servidor(corpo_erro)).complete(MENSAGENS, Diagnosis, _params())
    limitado = httpx2.Response(200, json={"error": {"message": "muitas", "code": 429}})
    with pytest.raises(LLMRateLimited) as exc:
        _cliente(Servidor(limitado)).complete(MENSAGENS, Diagnosis, _params())
    assert str(exc.value) == RATE_LIMIT_MESSAGE


def test_mensagem_de_erro_nao_vaza_a_chave() -> None:
    servidor = Servidor(httpx2.Response(401, json={"error": {"message": "chave inválida"}}))
    with pytest.raises(LLMUnavailable) as exc:
        _cliente(servidor).complete(MENSAGENS, Diagnosis, _params())
    assert CHAVE not in str(exc.value) and CHAVE not in repr(exc.value)


def test_fabrica_fake_por_padrao(settings: Settings) -> None:
    assert isinstance(build_llm_client(settings), FakeLLM)


def test_fabrica_openrouter_sem_chave_falha_no_uso_com_mensagem_clara() -> None:
    cliente = build_llm_client(Settings(llm_provider="openrouter"))
    assert isinstance(cliente, MissingKeyLLM)
    with pytest.raises(LLMUnavailable, match="OPENROUTER_API_KEY") as exc:
        cliente.complete(MENSAGENS, Diagnosis, _params())
    assert str(exc.value) == MISSING_KEY_MESSAGE


def test_fabrica_openrouter_com_chave_cria_o_adaptador_real() -> None:
    settings = Settings(llm_provider="openrouter", openrouter_api_key=SecretStr(CHAVE))
    assert isinstance(build_llm_client(settings), OpenAICompatClient)


# --- controle de raciocínio (ADR 0027) ---------------------------------------------------------------


def _params_raciocinio(modo: ReasoningMode) -> LLMParams:
    return LLMParams(model="vendor/modelo:free", temperature=0.1, max_tokens=500, structured_mode="json_schema",
                     reasoning=modo)


def test_raciocinio_default_nao_envia_o_parametro() -> None:
    servidor = Servidor(_ok())
    _cliente(servidor).complete(MENSAGENS, Diagnosis, _params())
    assert "reasoning" not in servidor.corpo()


@pytest.mark.parametrize(
    ("modo", "esperado"),
    [
        ("off", {"enabled": False}),
        ("none", {"effort": "none"}),
        ("low", {"effort": "low"}),
        ("medium", {"effort": "medium"}),
        ("high", {"effort": "high"}),
    ],
)
def test_raciocinio_vai_no_corpo_da_requisicao(modo: ReasoningMode, esperado: dict) -> None:
    servidor = Servidor(_ok())
    _cliente(servidor).complete(MENSAGENS, Diagnosis, _params_raciocinio(modo))
    assert servidor.corpo()["reasoning"] == esperado


def test_raciocinio_obrigatorio_recusado_pelo_provedor_vira_llm_unavailable_com_a_causa() -> None:
    """Resposta real medida no modelo padrão: HTTP 400 dizendo que o raciocínio é obrigatório."""
    mensagem = "Reasoning is mandatory for this endpoint and cannot be disabled."
    recusa = httpx2.Response(400, json={"error": {"message": mensagem}})
    with pytest.raises(LLMUnavailable, match="mandatory"):
        _cliente(Servidor(recusa)).complete(MENSAGENS, Diagnosis, _params_raciocinio("off"))


def test_settings_aceita_so_modos_de_raciocinio_validos() -> None:
    assert Settings().llm_reasoning == "default"
    assert Settings(llm_reasoning="off").llm_reasoning == "off"
    with pytest.raises(ValueError):
        Settings(llm_reasoning="desligado")  # type: ignore[arg-type]
