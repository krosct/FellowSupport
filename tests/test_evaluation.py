"""Testes das regras da avaliação manual pela rubrica (ADR 0020): validação das notas, execução avaliável e total.

A gravação das notas acontece só dentro da comparação e é testada em ``tests/test_comparison.py``.
"""

import json

import pytest

from app.domain import rubric
from app.domain.errors import ValidationFailed
from app.domain.evaluation import RubricScores, parse_scores, require_evaluable, total_score


def notas(**mudancas: object) -> dict:
    """Avaliação válida (3 critérios); ``notas(clarity=...)`` sobrescreve um critério."""
    base = {key: {"score": 4, "justification": f"Justificativa de {key}."} for key in rubric.CRITERIA_KEYS}
    return {**base, **mudancas}


def test_modelo_de_notas_vem_da_rubrica() -> None:
    """Os campos do modelo são exatamente os critérios da rubrica, na ordem dela (SSOT)."""
    assert tuple(RubricScores.model_fields) == rubric.CRITERIA_KEYS


def test_notas_validas_aparam_a_justificativa() -> None:
    parsed = parse_scores(notas(clarity={"score": 5, "justification": "  Bem organizada.  "})).model_dump()
    assert parsed["clarity"] == {"score": 5, "justification": "Bem organizada."}
    assert list(parsed) == list(rubric.CRITERIA_KEYS)


@pytest.mark.parametrize("nota", [0, 6, -1, 4.5, 4.0, "4", True, None])
def test_nota_fora_de_1_a_5_ou_nao_inteira_e_recusada(nota: object) -> None:
    with pytest.raises(ValidationFailed, match="Clareza: a nota deve ser um inteiro de 1 a 5"):
        parse_scores(notas(clarity={"score": nota, "justification": "ok"}))


@pytest.mark.parametrize("justificativa", ["", "   ", "\n\t"])
def test_justificativa_vazia_e_recusada(justificativa: str) -> None:
    with pytest.raises(ValidationFailed, match="Adequação ao nível do cliente: a justificativa é obrigatória"):
        parse_scores(notas(customer_fit={"score": 3, "justification": justificativa}))


def test_justificativa_longa_demais_e_recusada() -> None:
    longa = "x" * (rubric.JUSTIFICATION_MAX_CHARS + 1)
    with pytest.raises(ValidationFailed, match="passa de 500 caracteres"):
        parse_scores(notas(actionability={"score": 3, "justification": longa}))


def test_criterio_faltando_ou_desconhecido_e_recusado() -> None:
    sem_um = notas()
    del sem_um["actionability"]
    with pytest.raises(ValidationFailed, match="Acionabilidade: avaliação ausente"):
        parse_scores(sem_um)
    with pytest.raises(ValidationFailed, match="critério desconhecido: extra"):
        parse_scores({**notas(), "extra": {"score": 3, "justification": "x"}})
    with pytest.raises(ValidationFailed, match="Clareza: justificativa ausente"):
        parse_scores(notas(clarity={"score": 3}))


def test_varios_problemas_vem_em_uma_mensagem_so() -> None:
    with pytest.raises(ValidationFailed) as exc:
        parse_scores(notas(clarity={"score": 9, "justification": ""}, customer_fit={"score": 0, "justification": "x"}))
    assert "Clareza" in str(exc.value) and "Adequação" in str(exc.value) and "justificativa" in str(exc.value)


def test_corpo_que_nao_e_objeto_e_recusado() -> None:
    with pytest.raises(ValidationFailed, match="envie um objeto"):
        parse_scores([1, 2, 3])


def test_execucao_com_erro_nao_pode_ser_avaliada(make_record) -> None:
    require_evaluable(make_record(output={"opening": "x"}))  # execução ok passa
    erro = {"type": "InvalidLLMOutput", "message": "x"}
    with pytest.raises(ValidationFailed, match="terminou em erro"):
        require_evaluable(make_record(run_id="eeeeeeeeeeee", status="error", error=erro))


def test_total_soma_os_tres_criterios() -> None:
    evaluation = json.loads(json.dumps(notas(clarity={"score": 5, "justification": "a"})))
    assert total_score(evaluation) == 5 + 4 + 4
