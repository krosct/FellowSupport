"""Testes da avaliação manual pela rubrica (ADR 0020): validação das notas e gravação atômica."""

import json
from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.config import Settings
from app.container import build_container
from app.domain import rubric
from app.domain.errors import NotFound, ValidationFailed
from app.domain.evaluation import RubricScores, parse_scores, total_score
from app.services.evaluation import EvaluationContext, evaluate_manual

RUN_ID = "abc123def456"


def notas(**mudancas: object) -> dict:
    """Avaliação válida (3 critérios); ``notas(clarity=...)`` sobrescreve um critério."""
    base = {key: {"score": 4, "justification": f"Justificativa de {key}."} for key in rubric.CRITERIA_KEYS}
    return {**base, **mudancas}


def relogio_fixo(tz: ZoneInfo) -> datetime:
    """Relógio de teste: 15h UTC de 20/11/2026 (12h em Brasília)."""
    return datetime(2026, 11, 20, 15, 0, 0, tzinfo=ZoneInfo("UTC")).astimezone(tz)


@pytest.fixture
def ctx(settings: Settings, make_record) -> EvaluationContext:
    """Contexto real do container (provedor fake, dados em pasta temporária) com uma execução salva."""
    contexto = replace(build_container(settings).evaluation, clock=relogio_fixo)
    contexto.runs.save(make_record(output={"opening": "x"}))
    return contexto


def test_modelo_de_notas_vem_da_rubrica() -> None:
    """Os campos do modelo são exatamente os critérios da rubrica, na ordem dela (SSOT)."""
    assert tuple(RubricScores.model_fields) == rubric.CRITERIA_KEYS


def test_grava_evaluation_no_registro_com_autor_e_horario_de_brasilia(ctx: EvaluationContext) -> None:
    # Salva a nota manual e confere autoria e fuso horário.
    stored = evaluate_manual(ctx, RUN_ID, notas(clarity={"score": 5, "justification": "  Bem organizada.  "}))
    evaluation = stored.record.evaluation
    assert evaluation is not None
    assert evaluation["clarity"] == {"score": 5, "justification": "Bem organizada."}  # justificativa aparada
    assert evaluation["evaluator"] == "candidato"
    assert evaluation["evaluated_at"] == "2026-11-20T12:00:00-03:00"  # UTC 15h convertido para Brasília
    # A estrutura tem um item por critério com score e justification.
    assert list(evaluation)[:3] == list(rubric.CRITERIA_KEYS)
    # Gravado de fato, e o resto do registro (saída, perfil) continua intacto.
    do_disco = ctx.runs.get(RUN_ID).record
    assert do_disco.evaluation == evaluation and do_disco.output == {"opening": "x"}


def test_reavaliar_substitui_a_avaliacao_anterior(ctx: EvaluationContext) -> None:
    primeira = evaluate_manual(ctx, RUN_ID, notas())
    stored = evaluate_manual(ctx, RUN_ID, notas(actionability={"score": 2, "justification": "Faltou o próximo passo."}))
    assert stored.record.evaluation is not None and stored.record.evaluation["actionability"]["score"] == 2
    assert stored.saved_path == primeira.saved_path  # o mesmo arquivo foi substituído, não surgiu outro


@pytest.mark.parametrize("nota", [0, 6, -1, 4.5, 4.0, "4", True, None])
def test_nota_fora_de_1_a_5_ou_nao_inteira_e_recusada(ctx: EvaluationContext, nota: object) -> None:
    with pytest.raises(ValidationFailed, match="Clareza: a nota deve ser um inteiro de 1 a 5"):
        evaluate_manual(ctx, RUN_ID, notas(clarity={"score": nota, "justification": "ok"}))
    assert ctx.runs.get(RUN_ID).record.evaluation is None  # nada foi gravado


@pytest.mark.parametrize("justificativa", ["", "   ", "\n\t"])
def test_justificativa_vazia_e_recusada(ctx: EvaluationContext, justificativa: str) -> None:
    with pytest.raises(ValidationFailed, match="Adequação ao nível do cliente: a justificativa é obrigatória"):
        evaluate_manual(ctx, RUN_ID, notas(customer_fit={"score": 3, "justification": justificativa}))


def test_justificativa_longa_demais_e_recusada(ctx: EvaluationContext) -> None:
    longa = "x" * (rubric.JUSTIFICATION_MAX_CHARS + 1)
    with pytest.raises(ValidationFailed, match="passa de 500 caracteres"):
        evaluate_manual(ctx, RUN_ID, notas(actionability={"score": 3, "justification": longa}))


def test_criterio_faltando_ou_desconhecido_e_recusado(ctx: EvaluationContext) -> None:
    sem_um = notas()
    del sem_um["actionability"]
    with pytest.raises(ValidationFailed, match="Acionabilidade: avaliação ausente"):
        evaluate_manual(ctx, RUN_ID, sem_um)
    with pytest.raises(ValidationFailed, match="critério desconhecido: extra"):
        evaluate_manual(ctx, RUN_ID, {**notas(), "extra": {"score": 3, "justification": "x"}})
    with pytest.raises(ValidationFailed, match="Clareza: justificativa ausente"):
        evaluate_manual(ctx, RUN_ID, notas(clarity={"score": 3}))


def test_varios_problemas_vem_em_uma_mensagem_so(ctx: EvaluationContext) -> None:
    with pytest.raises(ValidationFailed) as exc:
        ruins = notas(clarity={"score": 9, "justification": ""}, customer_fit={"score": 0, "justification": "x"})
        evaluate_manual(ctx, RUN_ID, ruins)
    assert "Clareza" in str(exc.value) and "Adequação" in str(exc.value) and "justificativa" in str(exc.value)


def test_corpo_que_nao_e_objeto_e_recusado() -> None:
    with pytest.raises(ValidationFailed, match="envie um objeto"):
        parse_scores([1, 2, 3])


def test_execucao_inexistente_e_not_found(ctx: EvaluationContext) -> None:
    with pytest.raises(NotFound):
        evaluate_manual(ctx, "ffffffffffff", notas())


def test_execucao_com_erro_nao_pode_ser_avaliada(ctx: EvaluationContext, make_record) -> None:
    erro = {"type": "InvalidLLMOutput", "message": "x"}
    ctx.runs.save(make_record(run_id="eeeeeeeeeeee", status="error", error=erro))
    with pytest.raises(ValidationFailed, match="terminou em erro"):
        evaluate_manual(ctx, "eeeeeeeeeeee", notas())


def test_total_soma_os_tres_criterios() -> None:
    evaluation = json.loads(json.dumps(notas(clarity={"score": 5, "justification": "a"})))
    assert total_score(evaluation) == 5 + 4 + 4
