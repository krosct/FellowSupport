"""Testes de ``POST /api/generate`` e ``GET /api/prompt-versions`` via TestClient (sem rede, ADR 0016)."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.adapters.api.main import ERROR_STATUS, create_app
from app.config import Settings
from app.container import build_container
from app.domain.errors import InvalidLLMOutput, LLMRateLimited, LLMUnavailable, NotFound, ValidationFailed
from app.domain.models import OUTPUT_SCHEMAS, ContentType, Diagnosis, FlowSummary, ResolutionSteps
from tests.support import LATEST_VERSION, LLMPorSchema, LLMRoteirizado

CORPO = {"profile_id": "marta", "ticket_id": "t-2fa", "content_type": "diagnosis"}


def _cliente(settings: Settings, llm=None) -> TestClient:
    # Cria TestClient isolado com container de teste e sem servir arquivos estáticos.
    return TestClient(create_app(build_container(settings, llm=llm), frontend_dist=None))


def _arquivos(settings: Settings) -> list[Path]:
    return sorted((settings.data_dir / "runs").rglob("*.json"))


def test_gera_diagnostico_com_ticket_do_catalogo(settings: Settings) -> None:
    r = _cliente(settings).post("/api/generate", json=CORPO)
    assert r.status_code == 200
    corpo = r.json()
    run = corpo["run"]
    Diagnosis.model_validate(run["output"])
    assert run["status"] == "ok" and run["prompt_version"] == LATEST_VERSION and run["provider"] == "fake"
    assert run["customer_profile"]["name"] == "Dona Marta"
    [arquivo] = _arquivos(settings)
    assert corpo["saved_path"] == str(arquivo)
    assert json.loads(arquivo.read_text(encoding="utf-8"))["run_id"] == run["run_id"]


@pytest.mark.parametrize("tipo", [t for t in ContentType])
def test_gera_cada_tipo_com_saida_valida_pelo_schema(settings: Settings, tipo: ContentType) -> None:
    r = _cliente(settings).post("/api/generate", json={**CORPO, "content_type": tipo.value})
    assert r.status_code == 200
    run = r.json()["run"]
    assert run["content_type"] == tipo.value and run["status"] == "ok"
    OUTPUT_SCHEMAS[tipo].model_validate(run["output"])
    # Só o fluxograma traz o desenho ASCII em "rendered".
    assert (run["rendered"] is not None) == (tipo is ContentType.FLOW_SUMMARY)


def test_tipo_de_conteudo_desconhecido_e_422(settings: Settings) -> None:
    assert _cliente(settings).post("/api/generate", json={**CORPO, "content_type": "inexistente"}).status_code == 422


def test_tipo_padrao_e_diagnostico(settings: Settings) -> None:
    r = _cliente(settings).post("/api/generate", json={"profile_id": "marta", "ticket_id": "t-webhook"})
    assert r.json()["run"]["content_type"] == "diagnosis"


@pytest.mark.parametrize(
    ("corpo", "status", "trecho"),
    [
        ({**CORPO, "profile_id": "ninguem"}, 404, "Perfil não encontrado"),
        ({**CORPO, "ticket_id": "t-nada"}, 404, "Ticket não encontrado"),
        ({**CORPO, "prompt_version": "v99"}, 404, "v99"),
        ({"profile_id": "marta"}, 422, "ticket_id"),  # o ticket é sempre um do catálogo
    ],
)
def test_erros_de_entrada_viram_http_com_mensagem(settings: Settings, corpo: dict, status: int, trecho: str) -> None:
    r = _cliente(settings).post("/api/generate", json=corpo)
    assert r.status_code == status
    assert trecho in str(r.json()["detail"])
    assert _arquivos(settings) == []


def test_ticket_acima_do_limite_e_422(settings: Settings) -> None:
    pequeno = Settings(
        llm_provider="fake", max_ticket_chars=20, catalog_dir=settings.catalog_dir,
        prompts_dir=settings.prompts_dir, data_dir=settings.data_dir,
    )
    from app.services.catalog import create_ticket

    longo = create_ticket(build_container(settings).tickets, "Longo", "x" * 21, settings.max_ticket_chars).id
    r = _cliente(pequeno).post("/api/generate", json={"profile_id": "marta", "ticket_id": longo})
    assert r.status_code == 422 and "limite é 20" in r.json()["detail"]


def test_tipo_de_conteudo_desconhecido_e_recusado_pelo_schema(settings: Settings) -> None:
    r = _cliente(settings).post("/api/generate", json={**CORPO, "content_type": "poema"})
    assert r.status_code == 422


@pytest.mark.parametrize(
    ("erro", "status"),
    [(LLMUnavailable("fora do ar"), 503), (LLMRateLimited("muitas"), 429)],
)
def test_erros_do_provedor_viram_503_e_429_e_gravam_a_execucao(
    settings: Settings, erro: Exception, status: int
) -> None:
    r = _cliente(settings, LLMRoteirizado(erro)).post("/api/generate", json=CORPO)
    assert r.status_code == status and r.json()["detail"] == str(erro)
    [arquivo] = _arquivos(settings)
    assert json.loads(arquivo.read_text(encoding="utf-8"))["status"] == "error"


def test_saida_invalida_apos_reparo_e_502(settings: Settings) -> None:
    r = _cliente(settings, LLMRoteirizado("{}", "{}")).post("/api/generate", json=CORPO)
    assert r.status_code == 502 and "reparo" in r.json()["detail"]
    [arquivo] = _arquivos(settings)
    assert json.loads(arquivo.read_text(encoding="utf-8"))["error"]["type"] == "InvalidLLMOutput"


def test_openrouter_sem_chave_responde_503_com_mensagem_clara(settings: Settings) -> None:
    sem_chave = Settings(
        llm_provider="openrouter", catalog_dir=settings.catalog_dir,
        prompts_dir=settings.prompts_dir, data_dir=settings.data_dir,
    )
    r = _cliente(sem_chave).post("/api/generate", json=CORPO)
    assert r.status_code == 503 and "OPENROUTER_API_KEY" in r.json()["detail"]


def test_mapa_de_erros_cobre_todas_as_excecoes_do_plano() -> None:
    assert ERROR_STATUS[LLMUnavailable] == 503 and ERROR_STATUS[LLMRateLimited] == 429
    assert ERROR_STATUS[InvalidLLMOutput] == 502 and ERROR_STATUS[NotFound] == 404
    assert ERROR_STATUS[ValidationFailed] == 422


def test_prompt_versions_lista_meta_e_marca_a_mais_nova_como_padrao(settings: Settings) -> None:
    from tests.support import LATEST_VERSION, seed_prompt_versions

    seed_prompt_versions(settings.prompts_dir, "v2", "v3")
    r = _cliente(settings).get("/api/prompt-versions")
    assert r.status_code == 200
    versoes = r.json()
    assert len(versoes) >= 3
    v1 = versoes[0]
    assert v1["version"] == "v1" and v1["based_on"] is None and v1["is_default"] is False
    assert len(v1["content_sha256"]) == 64
    assert isinstance(v1["changes"], list)
    # As versões derivadas registram a base e mudanças (as mudanças alimentam a aba Comparar).
    assert versoes[1]["version"] == "v2" and versoes[1]["based_on"] == "v1"
    assert {"what", "why", "expected_effect"} <= set(versoes[1]["changes"][0])
    # A padrão é sempre a mais nova (ADR 0039): só a última da lista é marcada.
    assert all(not item["is_default"] for item in versoes[:-1])
    ultima = versoes[-1]
    assert ultima["version"] == LATEST_VERSION and ultima["is_default"] is True


def test_meta_traz_niveis_de_confianca(settings: Settings) -> None:
    meta = _cliente(settings).get("/api/meta").json()
    assert [o["value"] for o in meta["confidence_levels"]] == ["baixa", "média", "alta"]
    assert [o["label"] for o in meta["confidence_levels"]] == ["Baixa", "Média", "Alta"]


# --- modo all ---------------------------------------------------------------------------------------


def test_all_devolve_um_item_por_tipo_com_o_json_de_cada_execucao(settings: Settings) -> None:
    r = _cliente(settings).post("/api/generate", json={**CORPO, "content_type": "all"})
    assert r.status_code == 200
    itens = r.json()["results"]
    assert [i["content_type"] for i in itens] == [t.value for t in ContentType]
    arquivos = {str(a) for a in _arquivos(settings)}
    assert len(arquivos) == 4
    for item in itens:
        assert item["error"] is None and item["run"]["status"] == "ok"
        assert item["saved_path"] in arquivos
        OUTPUT_SCHEMAS[ContentType(item["content_type"])].model_validate(item["run"]["output"])


def test_all_com_falha_parcial_responde_200_com_o_erro_do_tipo(settings: Settings) -> None:
    llm = LLMPorSchema({ResolutionSteps: LLMUnavailable("fora do ar"), FlowSummary: "{}"})
    r = _cliente(settings, llm).post("/api/generate", json={**CORPO, "content_type": "all"})
    assert r.status_code == 200
    por_tipo = {i["content_type"]: i for i in r.json()["results"]}
    assert por_tipo["diagnosis"]["run"]["status"] == "ok" and por_tipo["diagnosis"]["error"] is None
    assert por_tipo["resolution_steps"]["error"] == {"type": "LLMUnavailable", "message": "fora do ar"}
    assert por_tipo["resolution_steps"]["run"]["status"] == "error"  # o JSON de erro também foi gravado
    assert por_tipo["flow_summary"]["error"]["type"] == "InvalidLLMOutput"
    assert len(_arquivos(settings)) == 4


def test_all_com_todas_as_falhas_responde_com_o_erro_mapeado(settings: Settings) -> None:
    llm = LLMPorSchema({t: LLMRateLimited("429") for t in OUTPUT_SCHEMAS.values()})
    r = _cliente(settings, llm).post("/api/generate", json={**CORPO, "content_type": "all"})
    assert r.status_code == 429 and "429" in r.json()["detail"]


@pytest.mark.parametrize(
    ("corpo", "status"),
    [
        ({**CORPO, "profile_id": "ninguem"}, 404),
        ({"profile_id": "marta", "content_type": "all"}, 422),
        ({**CORPO, "prompt_version": "v99"}, 404),
    ],
)
def test_all_com_entrada_invalida_recusa_antes_de_gerar(settings: Settings, corpo: dict, status: int) -> None:
    llm = LLMPorSchema({})
    r = _cliente(settings, llm).post("/api/generate", json={**corpo, "content_type": "all"})
    assert r.status_code == status and llm.chamadas == [] and _arquivos(settings) == []


# --- cache (ADR 0028) --------------------------------------------------------------------------------


class _Contador(LLMPorSchema):
    """``LLMPorSchema`` sem respostas roteirizadas: cai no FakeLLM e conta as chamadas."""

    def __init__(self) -> None:
        super().__init__({})


def test_segunda_chamada_igual_e_cache_hit_sem_chamar_o_llm(settings: Settings) -> None:
    llm = _Contador()
    cliente = _cliente(settings, llm)
    primeira = cliente.post("/api/generate", json=CORPO).json()["run"]
    segunda = cliente.post("/api/generate", json=CORPO).json()["run"]
    assert len(llm.chamadas) == 1
    assert primeira["cache_hit"] is False and segunda["cache_hit"] is True
    assert segunda["source_run_id"] == primeira["run_id"] and segunda["latency_ms"] < 50
    assert segunda["output"] == primeira["output"]


def test_use_cache_false_gera_de_novo(settings: Settings) -> None:
    llm = _Contador()
    cliente = _cliente(settings, llm)
    cliente.post("/api/generate", json=CORPO)
    r = cliente.post("/api/generate", json={**CORPO, "use_cache": False, "confirm_replace": True}).json()["run"]
    assert r["cache_hit"] is False and len(llm.chamadas) == 2


def test_use_cache_invalido_e_422(settings: Settings) -> None:
    assert _cliente(settings).post("/api/generate", json={**CORPO, "use_cache": "talvez"}).status_code == 422


def test_all_cada_tipo_consulta_o_cache_sozinho(settings: Settings) -> None:
    # Gera só diagnosis primeiro e depois verifica que o modo all reaproveita só ele do cache.
    llm = _Contador()
    cliente = _cliente(settings, llm)
    cliente.post("/api/generate", json=CORPO)  # só o diagnóstico
    itens = cliente.post("/api/generate", json={**CORPO, "content_type": "all"}).json()["results"]
    hits = {i["content_type"]: i["run"]["cache_hit"] for i in itens}
    assert hits == {"diagnosis": True, "resolution_steps": False, "clarifying_questions": False, "flow_summary": False}
    assert len(llm.chamadas) == 4
    again = cliente.post("/api/generate", json={**CORPO, "content_type": "all"}).json()["results"]
    assert all(i["run"]["cache_hit"] for i in again) and len(llm.chamadas) == 4
    forcado = {**CORPO, "content_type": "all", "use_cache": False, "confirm_replace": True}
    sem = cliente.post("/api/generate", json=forcado).json()["results"]
    assert not any(i["run"]["cache_hit"] for i in sem) and len(llm.chamadas) == 8


def test_sem_cache_sobre_entrada_existente_responde_409_com_todos_os_conflitos(settings: Settings) -> None:
    llm = _Contador()
    cliente = _cliente(settings, llm)
    cliente.post("/api/generate", json={**CORPO, "content_type": "all"})
    assert len(llm.chamadas) == 4
    r = cliente.post("/api/generate", json={**CORPO, "content_type": "all", "use_cache": False})
    corpo = r.json()
    assert r.status_code == 409 and corpo["code"] == "cache_replace_required"
    assert {c["content_type"] for c in corpo["conflicts"]} == {
        "diagnosis", "resolution_steps", "clarifying_questions", "flow_summary",
    }
    assert {"prompt_version", "run_id", "created_at"} <= set(corpo["conflicts"][0])
    assert len(llm.chamadas) == 4  # nada foi gerado
    # Repetindo o mesmo pedido com a confirmação, a geração acontece e o ponteiro é trocado.
    forcado = {**CORPO, "content_type": "all", "use_cache": False, "confirm_replace": True}
    ok = cliente.post("/api/generate", json=forcado)
    assert ok.status_code == 200 and len(llm.chamadas) == 8


def test_sem_cache_sem_entrada_anterior_nao_pede_confirmacao(settings: Settings) -> None:
    r = _cliente(settings, _Contador()).post("/api/generate", json={**CORPO, "use_cache": False})
    assert r.status_code == 200
