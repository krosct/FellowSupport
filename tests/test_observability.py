"""Testes do registro do corte por limite (ADR 0042) e do log de eventos em JSON Lines (ADR 0043), sem rede."""

import json
import stat
import threading
from pathlib import Path

import pytest

from app.adapters.storage.event_log import LOG_FILE_MODE, JsonLinesEventLog
from app.config import Settings
from app.container import Container, build_container
from app.domain import rubric
from app.domain.errors import InvalidLLMOutput
from app.domain.llm_output import truncation_message
from app.domain.models import ContentType
from app.ports.events import EVENT_COMPARISON, EVENT_EVALUATION, EVENT_GENERATION, EVENT_GENERATION_BATCH
from app.ports.llm import LLMResult
from app.services.comparison import save_comparison
from app.services.evaluation import evaluate_manual
from app.services.generators import generate, generate_all
from tests.support import LLMRoteirizado, gerar_versoes


def _eventos(settings: Settings, nome: str | None = None) -> list[dict]:
    """Eventos gravados no log do teste (todas as linhas precisam ser JSON íntegro)."""
    linhas = settings.log_file.read_text(encoding="utf-8").splitlines()
    eventos = [json.loads(linha) for linha in linhas]
    return [e for e in eventos if nome is None or e["event"] == nome]


def _cortada(completion: int, provedor: str = "ProvedorX") -> LLMResult:
    """Resposta de um modelo de raciocínio cortada sem JSON, como as das execuções com erro."""
    return LLMResult(
        text="", parsed=None, latency_ms=13942, model_used="vendor/efetivo", finish_reason="length",
        provider_used=provedor, response_id="gen-abc",
        usage={"prompt_tokens": 1139, "completion_tokens": completion, "reasoning_tokens": 2077},
    )


def _notas(base: int = 4) -> dict:
    return {key: {"score": base, "justification": f"Motivo de {key}."} for key in rubric.CRITERIA_KEYS}


# --- mensagem do corte (ponto 1) ----------------------------------------------------------------------------


def test_corte_abaixo_do_limite_culpa_o_provedor_e_nao_manda_aumentar_o_limite() -> None:
    msg = truncation_message(max_tokens=12000, completion_tokens=2400, reasoning_tokens=2077, provider="ProvedorX")
    assert "2400 tokens (2077 em raciocínio)" in msg and "limite configurado de 12000" in msg
    assert "ProvedorX" in msg and "não resolve" in msg


def test_corte_no_limite_configurado_manda_aumentar_o_limite() -> None:
    msg = truncation_message(max_tokens=1500, completion_tokens=1500, reasoning_tokens=1500, provider="P")
    assert "limite configurado de 1500" in msg and msg.endswith("Aumente LLM_MAX_TOKENS.")


# --- gasto e provedor da execução cortada (pontos 2 e 3) ----------------------------------------------------


def test_execucao_cortada_grava_gasto_modelo_e_provedor_sem_tentar_reparo(settings: Settings) -> None:
    llm = LLMRoteirizado(_cortada(2400))
    container = build_container(settings, llm=llm)
    with pytest.raises(InvalidLLMOutput, match="ProvedorX"):
        generate(container.generation, content_type=ContentType.DIAGNOSIS, profile_id="marta", ticket_id="t-2fa")

    assert len(llm.chamadas) == 1  # sem reparo: comportamento do ADR 0026 mantido
    [arquivo] = sorted((settings.data_dir / "runs").rglob("*.json"))
    salvo = json.loads(arquivo.read_text(encoding="utf-8"))
    assert salvo["status"] == "error" and salvo["attempts"] == 1
    assert salvo["usage"] == {"prompt_tokens": 1139, "completion_tokens": 2400, "reasoning_tokens": 2077}
    assert salvo["model_used"] == "vendor/efetivo"
    [chamada] = salvo["llm_calls"]
    assert chamada["provider_used"] == "ProvedorX" and chamada["response_id"] == "gen-abc"
    assert chamada["finish_reason"] == "length" and chamada["json_extracted"] is False
    assert "abaixo do limite configurado" in chamada["problem"]


def test_chamadas_com_reparo_aparecem_as_duas_com_o_motivo_da_recusa(settings: Settings) -> None:
    from tests.test_generators import _diagnostico_valido

    llm = LLMRoteirizado("sem json nenhum", _diagnostico_valido())
    container = build_container(settings, llm=llm)
    resultado = generate(
        container.generation, content_type=ContentType.DIAGNOSIS, profile_id="marta", ticket_id="t-2fa"
    )
    primeira, segunda = resultado.record.llm_calls
    assert (primeira.attempt, segunda.attempt) == (1, 2)
    assert primeira.problem and not primeira.json_extracted
    assert segunda.problem is None and segunda.json_extracted


# --- eventos de geração -------------------------------------------------------------------------------------


def test_geracao_emite_um_evento_com_o_que_explica_o_resultado(settings: Settings) -> None:
    container = build_container(settings, llm=LLMRoteirizado(_cortada(2400)))
    with pytest.raises(InvalidLLMOutput):
        generate(container.generation, content_type=ContentType.DIAGNOSIS, profile_id="marta", ticket_id="t-2fa")

    [evento] = _eventos(settings, EVENT_GENERATION)
    assert evento["status"] == "error" and evento["error"]["type"] == "InvalidLLMOutput"
    assert evento["ts"].endswith("-03:00")  # fuso de APP_TIMEZONE
    assert evento["customer"]["id"] == "marta" and evento["ticket"]["id"] == "t-2fa"
    assert evento["params"]["max_tokens"] == settings.llm_max_tokens
    assert evento["usage"]["completion_tokens"] == 2400
    assert evento["llm_calls"][0]["provider_used"] == "ProvedorX"
    assert evento["saved_path"].endswith(f"{evento['run_id']}.json")
    assert evento["batch_id"] is None


def test_evento_nao_leva_o_texto_do_ticket_nem_a_chave(settings: Settings) -> None:
    container = build_container(settings)
    resultado = generate(
        container.generation, content_type=ContentType.DIAGNOSIS, profile_id="marta", ticket_id="t-2fa"
    )
    bruto = settings.log_file.read_text(encoding="utf-8")
    assert resultado.record.ticket.text not in bruto  # ADR 0019: o texto fica no JSON da execução
    assert _eventos(settings, EVENT_GENERATION)[0]["ticket"]["chars"] == len(resultado.record.ticket.text)


def test_acerto_de_cache_tambem_e_registrado(settings: Settings) -> None:
    container = build_container(settings)
    for _ in range(2):
        generate(container.generation, content_type=ContentType.DIAGNOSIS, profile_id="marta", ticket_id="t-2fa")
    primeiro, segundo = _eventos(settings, EVENT_GENERATION)
    assert primeiro["cache_hit"] is False and segundo["cache_hit"] is True
    assert segundo["source_run_id"] == primeiro["run_id"] and segundo["llm_calls"] == []


def test_modo_all_liga_as_quatro_geracoes_ao_evento_do_lote(settings: Settings) -> None:
    container = build_container(settings)
    lote = generate_all(container.generation, profile_id="marta", ticket_id="t-2fa")

    geracoes = _eventos(settings, EVENT_GENERATION)
    [resumo] = _eventos(settings, EVENT_GENERATION_BATCH)
    assert len(geracoes) == 4 and {g["batch_id"] for g in geracoes} == {resumo["batch_id"]}
    assert resumo["ok"] == 4 and resumo["failed"] == []
    assert [r["run_id"] for r in resumo["results"]] == [i.result.record.run_id for i in lote.items if i.result]
    assert resumo["usage"]["completion_tokens"] == sum(g["usage"]["completion_tokens"] for g in geracoes)


# --- eventos de avaliação e comparação ----------------------------------------------------------------------


def test_avaliacao_manual_emite_notas_justificativas_e_total(settings: Settings) -> None:
    container = build_container(settings)
    run_id = generate(
        container.generation, content_type=ContentType.DIAGNOSIS, profile_id="marta", ticket_id="t-2fa"
    ).record.run_id
    evaluate_manual(container.evaluation, run_id, _notas(4))

    [evento] = _eventos(settings, EVENT_EVALUATION)
    assert evento["run_id"] == run_id and evento["comparison_id"] is None
    assert evento["total"] == 4 * len(rubric.CRITERIA_KEYS)
    assert evento["evaluation"]["clarity"]["justification"] == "Motivo de clarity."


@pytest.fixture
def container(settings: Settings) -> Container:
    return build_container(settings)


def test_comparacao_emite_a_avaliacao_de_cada_execucao_e_o_resultado(container: Container, settings: Settings) -> None:
    id1, id2 = gerar_versoes(container)
    stored = save_comparison(container.comparison, run_ids=[id1, id2], evaluations={id1: _notas(5), id2: _notas(3)})

    avaliacoes = _eventos(settings, EVENT_EVALUATION)
    assert {a["run_id"] for a in avaliacoes} == {id1, id2}
    assert {a["comparison_id"] for a in avaliacoes} == {stored.record.comparison_id}
    [evento] = _eventos(settings, EVENT_COMPARISON)
    assert evento["winner"] == "v1" and evento["saved_path"] == stored.saved_path
    assert [v["total"] for v in evento["versions"]] == [15, 9]


# --- adaptador JSON Lines -----------------------------------------------------------------------------------


def test_adaptador_acrescenta_linhas_json_com_permissao_restrita(tmp_path: Path) -> None:
    log = JsonLinesEventLog(tmp_path / "sub" / "eventos.log", "America/Sao_Paulo")
    log.emit("a", {"n": 1, "texto": "ação"})
    log.emit("b", {"caminho": tmp_path})  # valor fora do JSON vira texto, sem perder o evento
    linhas = log.path.read_text(encoding="utf-8").splitlines()
    assert [json.loads(linha)["event"] for linha in linhas] == ["a", "b"]
    assert "ação" in linhas[0]  # acentuação legível
    assert stat.S_IMODE(log.path.stat().st_mode) == LOG_FILE_MODE


def test_adaptador_nao_mistura_linhas_entre_threads(tmp_path: Path) -> None:
    log = JsonLinesEventLog(tmp_path / "eventos.log", "America/Sao_Paulo")
    threads = [
        threading.Thread(target=lambda i=i: [log.emit("t", {"i": i, "carga": "x" * 5000}) for _ in range(50)])
        for i in range(8)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    linhas = log.path.read_text(encoding="utf-8").splitlines()
    assert len(linhas) == 400 and all(json.loads(linha)["event"] == "t" for linha in linhas)


def test_falha_de_disco_no_log_nao_derruba_quem_emite(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    bloqueio = tmp_path / "arquivo"
    bloqueio.write_text("não é pasta")
    log = JsonLinesEventLog(bloqueio / "eventos.log", "America/Sao_Paulo")
    log.emit("x", {})  # não levanta
    assert "não foi possível gravar o evento x" in caplog.text


def test_log_padrao_fica_na_raiz_do_projeto(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import BASE_DIR

    monkeypatch.delenv("LOG_FILE")
    assert Settings().log_file == BASE_DIR / "fellowsupport.log"
