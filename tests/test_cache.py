"""Testes do cache de gerações (ADR 0010 e 0028): acerto sem chamar o LLM, invalidação, erros fora do cache."""

from __future__ import annotations

import json
import shutil
import threading
from dataclasses import replace
from pathlib import Path

import pytest

from app.adapters.llm.fake import FakeLLM
from app.config import Settings
from app.container import build_container
from app.domain.errors import InvalidLLMOutput, LLMUnavailable
from app.domain.models import CacheEntry, ContentType, Diagnosis, RunRecord
from app.ports.llm import ChatMessage, LLMParams, LLMResult
from app.services.generators import GenerationContext, generate, generate_all
from tests.support import LLMRoteirizado


class FakeContador:
    """``FakeLLM`` que conta as chamadas (seguro para threads): prova que o acerto de cache não chama o LLM."""

    def __init__(self) -> None:
        self._fake = FakeLLM()
        self._lock = threading.Lock()
        self.chamadas = 0

    def complete(self, messages: list[ChatMessage], schema: type, params: LLMParams) -> LLMResult:
        with self._lock:
            self.chamadas += 1
        return self._fake.complete(messages, schema, params)


def _ctx(settings: Settings, llm=None, **ajustes) -> GenerationContext:
    container = build_container(settings, llm=llm)
    ctx = container.generation
    return replace(ctx, config=replace(ctx.config, **ajustes)) if ajustes else ctx


def _gerar(ctx: GenerationContext, **kw):
    kw.setdefault("content_type", ContentType.DIAGNOSIS)
    kw.setdefault("profile_id", "marta")
    kw.setdefault("ticket_id", "t-2fa")
    return generate(ctx, **kw)


def _execucoes(settings: Settings) -> list[RunRecord]:
    arquivos = sorted((settings.data_dir / "runs").rglob("*.json"))
    return [RunRecord.model_validate_json(a.read_text(encoding="utf-8")) for a in arquivos]


def _entradas_de_cache(settings: Settings) -> list[Path]:
    return sorted((settings.data_dir / "cache").glob("*.json")) if (settings.data_dir / "cache").exists() else []


# --- acerto -------------------------------------------------------------------------------------------


def test_segunda_geracao_igual_e_cache_hit_sem_chamar_o_llm(settings: Settings) -> None:
    llm = FakeContador()
    ctx = _ctx(settings, llm)
    primeira = _gerar(ctx).record
    segunda = _gerar(ctx).record

    assert llm.chamadas == 1  # a segunda não chamou o LLM
    assert primeira.cache_hit is False and primeira.source_run_id is None
    assert segunda.cache_hit is True and segunda.source_run_id == primeira.run_id
    assert segunda.run_id != primeira.run_id and segunda.cache_key == primeira.cache_key
    assert segunda.output == primeira.output and segunda.status == "ok"
    assert segunda.model_used == primeira.model_used
    assert segunda.attempts == 0 and segunda.usage == {}  # nada foi gasto agora
    assert segunda.latency_ms < 50  # só o tempo de ler o cache (~0 ms)
    # O acerto também é uma execução gravada (evidência do reaproveitamento).
    assert {r.run_id for r in _execucoes(settings)} == {primeira.run_id, segunda.run_id}


def test_o_acerto_grava_o_proprio_registro_com_caminho_proprio(settings: Settings) -> None:
    ctx = _ctx(settings)
    primeira, segunda = _gerar(ctx), _gerar(ctx)
    assert primeira.saved_path != segunda.saved_path
    salvo = json.loads(Path(segunda.saved_path).read_text(encoding="utf-8"))
    assert salvo["cache_hit"] is True and salvo["source_run_id"] == primeira.record.run_id


def test_cache_aponta_para_a_execucao_de_origem(settings: Settings) -> None:
    ctx = _ctx(settings)
    primeira = _gerar(ctx).record
    [entrada] = _entradas_de_cache(settings)
    assert entrada.name == f"{primeira.cache_key}.json"
    assert json.loads(entrada.read_text(encoding="utf-8"))["source_run_id"] == primeira.run_id
    _gerar(ctx)
    # O acerto não cria entrada nova nem desloca a origem.
    assert json.loads(entrada.read_text(encoding="utf-8"))["source_run_id"] == primeira.run_id


def test_acerto_do_fluxograma_preserva_o_ascii(settings: Settings) -> None:
    ctx = _ctx(settings)
    primeira = _gerar(ctx, content_type=ContentType.FLOW_SUMMARY).record
    segunda = _gerar(ctx, content_type=ContentType.FLOW_SUMMARY).record
    assert segunda.cache_hit and segunda.rendered == primeira.rendered and segunda.rendered


def test_acerto_usa_o_ticket_e_o_perfil_da_chamada_atual(settings: Settings) -> None:
    """Texto livre equivalente (só espaços diferentes) acerta; o registro do acerto leva o ticket pedido agora."""
    llm = FakeContador()
    ctx = _ctx(settings, llm)
    _gerar(ctx, ticket_id=None, ticket_text="O SMS não   chega.")
    segunda = _gerar(ctx, ticket_id=None, ticket_text="  O SMS não chega.\n").record
    assert llm.chamadas == 1 and segunda.cache_hit
    assert segunda.ticket.text == "O SMS não chega."


# --- invalidação ---------------------------------------------------------------------------------------


MUDANCAS_DE_PEDIDO = {
    "perfil": {"profile_id": "bianca"},
    "ticket": {"ticket_id": "t-csv"},
    "texto livre": {"ticket_id": None, "ticket_text": "Outro relato."},
    "tipo": {"content_type": ContentType.RESOLUTION_STEPS},
}

MUDANCAS_DE_CONFIGURACAO = {
    "modelo": {"model": "outro/modelo:free"},
    "provedor": {"provider": "outro"},
    "temperatura": {"temperature": 0.9},
    "max_tokens": {"max_tokens": 4000},
    "modo estruturado": {"structured_mode": "json_object"},
    "raciocínio": {"reasoning": "off"},
}


@pytest.mark.parametrize("campo", list(MUDANCAS_DE_PEDIDO))
def test_mudar_o_pedido_invalida_o_cache(settings: Settings, campo: str) -> None:
    llm = FakeContador()
    ctx = _ctx(settings, llm)
    _gerar(ctx)
    segunda = _gerar(ctx, **MUDANCAS_DE_PEDIDO[campo]).record
    assert segunda.cache_hit is False and llm.chamadas == 2


@pytest.mark.parametrize("campo", list(MUDANCAS_DE_CONFIGURACAO))
def test_mudar_a_configuracao_invalida_o_cache(settings: Settings, campo: str) -> None:
    llm = FakeContador()
    ctx = _ctx(settings, llm)
    _gerar(ctx)
    outra = replace(ctx, config=replace(ctx.config, **MUDANCAS_DE_CONFIGURACAO[campo]))
    assert _gerar(outra).record.cache_hit is False
    assert llm.chamadas == 2


def test_mudar_a_versao_ou_o_conteudo_do_prompt_invalida_o_cache(settings: Settings, tmp_path: Path) -> None:
    prompts = tmp_path / "prompts"
    shutil.copytree(settings.prompts_dir, prompts)
    shutil.rmtree(prompts / "v2")  # a v2 real é substituída por uma cópia idêntica da v1 (só a versão difere)
    shutil.copytree(prompts / "v1", prompts / "v2")
    meta = json.loads((prompts / "v2" / "meta.json").read_text(encoding="utf-8"))
    (prompts / "v2" / "meta.json").write_text(json.dumps({**meta, "version": "v2", "based_on": "v1"}), encoding="utf-8")
    com_v2 = settings.model_copy(update={"prompts_dir": prompts})
    llm = FakeContador()
    ctx = _ctx(com_v2, llm)

    _gerar(ctx, prompt_version="v1")
    assert _gerar(ctx, prompt_version="v1").record.cache_hit is True
    assert _gerar(ctx, prompt_version="v2").record.cache_hit is False  # mesmos arquivos, versão diferente
    assert llm.chamadas == 2

    # Editar um arquivo sem criar versão nova muda o hash do prompt e também invalida (sem saída desatualizada).
    sistema = prompts / "v1" / "system.md"
    sistema.write_text(sistema.read_text(encoding="utf-8") + "\nLinha extra.\n", encoding="utf-8")
    assert _gerar(ctx, prompt_version="v1").record.cache_hit is False
    assert llm.chamadas == 3


# --- desligar o cache ----------------------------------------------------------------------------------


def test_use_cache_false_nao_le_nem_grava(settings: Settings) -> None:
    llm = FakeContador()
    ctx = _ctx(settings, llm)
    primeira = _gerar(ctx, use_cache=False).record
    assert _entradas_de_cache(settings) == []  # não gravou
    segunda = _gerar(ctx, use_cache=False).record
    assert llm.chamadas == 2 and not primeira.cache_hit and not segunda.cache_hit
    assert primeira.cache_key == segunda.cache_key  # a chave segue no registro, para achar equivalentes


def test_use_cache_false_ignora_uma_entrada_existente(settings: Settings) -> None:
    llm = FakeContador()
    ctx = _ctx(settings, llm)
    _gerar(ctx)
    assert _gerar(ctx, use_cache=False).record.cache_hit is False
    assert _gerar(ctx).record.cache_hit is True  # a entrada original continua valendo
    assert llm.chamadas == 2


def test_cache_enabled_false_no_settings_desliga_tudo(settings: Settings) -> None:
    sem_cache = settings.model_copy(update={"cache_enabled": False})
    llm = FakeContador()
    ctx = _ctx(sem_cache, llm)
    _gerar(ctx)
    assert _gerar(ctx).record.cache_hit is False and llm.chamadas == 2
    assert _entradas_de_cache(settings) == []


# --- erros nunca entram no cache -----------------------------------------------------------------------


def test_execucao_com_erro_do_provedor_nao_entra_no_cache(settings: Settings) -> None:
    ok = FakeLLM().complete([], Diagnosis, LLMParams("m", 0.1, 10, "prompt")).text
    llm = LLMRoteirizado(LLMUnavailable("fora do ar"), ok)
    ctx = _ctx(settings, llm)
    with pytest.raises(LLMUnavailable):
        _gerar(ctx)
    assert _entradas_de_cache(settings) == []
    [erro] = _execucoes(settings)
    assert erro.status == "error" and erro.cache_key  # leva a chave, mas não alimenta o cache
    segunda = _gerar(ctx).record  # a próxima tentativa chama o LLM de novo
    assert segunda.status == "ok" and segunda.cache_hit is False and len(llm.chamadas) == 2
    [entrada] = _entradas_de_cache(settings)
    assert json.loads(entrada.read_text(encoding="utf-8"))["source_run_id"] == segunda.run_id


def test_saida_invalida_apos_reparo_nao_entra_no_cache(settings: Settings) -> None:
    ctx = _ctx(settings, LLMRoteirizado("{}", "{}"))
    with pytest.raises(InvalidLLMOutput):
        _gerar(ctx)
    assert _entradas_de_cache(settings) == []


def test_cache_apontando_para_execucao_de_erro_vale_como_ausente(settings: Settings) -> None:
    ctx = _ctx(settings, LLMRoteirizado(LLMUnavailable("x")))
    with pytest.raises(LLMUnavailable):
        _gerar(ctx)
    [erro] = _execucoes(settings)
    ctx.cache.put(CacheEntry(cache_key=erro.cache_key, source_run_id=erro.run_id, created_at=erro.timestamp))
    llm = FakeContador()
    assert _gerar(_ctx(settings, llm)).record.cache_hit is False and llm.chamadas == 1


def test_cache_apontando_para_execucao_apagada_gera_de_novo_e_se_cura(settings: Settings) -> None:
    llm = FakeContador()
    ctx = _ctx(settings, llm)
    primeira = _gerar(ctx)
    Path(primeira.saved_path).unlink()
    segunda = _gerar(ctx).record
    assert segunda.cache_hit is False and llm.chamadas == 2
    assert _gerar(ctx).record.source_run_id == segunda.run_id  # o ponteiro foi regravado


# --- modo all --------------------------------------------------------------------------------------------


def test_all_consulta_o_cache_de_cada_tipo_de_forma_independente(settings: Settings) -> None:
    llm = FakeContador()
    ctx = _ctx(settings, llm)
    _gerar(ctx, content_type=ContentType.DIAGNOSIS)
    assert llm.chamadas == 1

    lote = generate_all(ctx, profile_id="marta", ticket_id="t-2fa")
    por_tipo = {i.content_type: i.result.record for i in lote.items}
    assert por_tipo[ContentType.DIAGNOSIS].cache_hit is True  # veio do cache
    assert all(not por_tipo[t].cache_hit for t in ContentType if t is not ContentType.DIAGNOSIS)
    assert llm.chamadas == 4  # +3: só os tipos sem equivalente

    todos = generate_all(ctx, profile_id="marta", ticket_id="t-2fa")
    assert all(i.result.record.cache_hit for i in todos.items) and llm.chamadas == 4


def test_all_com_use_cache_false_gera_os_quatro_de_novo(settings: Settings) -> None:
    llm = FakeContador()
    ctx = _ctx(settings, llm)
    generate_all(ctx, profile_id="marta", ticket_id="t-2fa")
    lote = generate_all(ctx, profile_id="marta", ticket_id="t-2fa", use_cache=False)
    assert not any(i.result.record.cache_hit for i in lote.items) and llm.chamadas == 8
