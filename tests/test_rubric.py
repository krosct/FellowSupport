"""Testes da rubrica fixa (item 5 do PDF)."""

from __future__ import annotations

from app.domain import rubric


def test_tres_criterios_na_ordem_do_pdf() -> None:
    assert rubric.CRITERIA_KEYS == ("clarity", "customer_fit", "actionability")


def test_escala_de_1_a_5_com_rotulos() -> None:
    assert (rubric.SCORE_MIN, rubric.SCORE_MAX) == (1, 5)
    assert list(rubric.SCORE_LABELS) == [1, 2, 3, 4, 5]
    assert rubric.SCORE_LABELS[1] == "insuficiente"
    assert rubric.SCORE_LABELS[5] == "excelente"


def test_validacao_de_nota() -> None:
    assert all(rubric.is_valid_score(n) for n in range(1, 6))
    assert not any(rubric.is_valid_score(n) for n in (0, 6, -1))


def test_rubric_as_dict_e_serializavel() -> None:
    data = rubric.rubric_as_dict()
    assert [c["key"] for c in data["criteria"]] == list(rubric.CRITERIA_KEYS)
    assert data["scale"]["labels"]["3"] == "adequado"
