"""Testes do schema ``Diagnosis``: formato válido, limites e regras cruzadas (ADR 0004)."""

from __future__ import annotations

import copy

import pytest
from pydantic import ValidationError

from app.domain.models import (
    DIAGNOSIS_MAX_HYPOTHESES,
    DIAGNOSIS_MIN_HYPOTHESES,
    Confidence,
    Diagnosis,
)


def _valid() -> dict:
    """Diagnóstico mínimo válido, copiado e alterado por cada teste."""
    return {
        "hypotheses": [
            {"id": "H1", "description": "Operadora bloqueia o SMS.", "probability_pct": 60,
             "evidence_for": ["Outros SMS chegam"], "evidence_against": []},
            {"id": "H2", "description": "Número antigo no cadastro.", "probability_pct": 30,
             "evidence_for": ["Trocou de chip"], "evidence_against": ["Número continua o mesmo"]},
        ],
        "available_evidence": ["SMS não chega há um dia"],
        "missing_information": [{"item": "Modelo do celular", "why_it_matters": "Filtro de remetente."}],
        "probable_conclusion": {"summary": "Bloqueio de SMS curto.", "hypothesis_id": "H1", "confidence": "média"},
        "customer_summary": "O código não chega por causa do chip.",
    }


def test_diagnostico_valido_e_sem_campo_de_raciocinio() -> None:
    d = Diagnosis.model_validate(_valid())
    assert d.probable_conclusion.confidence is Confidence.MEDIA
    # O schema não oferece lugar para cadeia de raciocínio (item 1 do PDF).
    assert not any("reason" in nome or "thought" in nome for nome in Diagnosis.model_fields)


def test_campo_extra_e_recusado() -> None:
    dados = _valid()
    dados["reasoning"] = "passo a passo interno"
    with pytest.raises(ValidationError):
        Diagnosis.model_validate(dados)


def test_json_schema_fecha_objetos_e_exige_todos_os_campos() -> None:
    """Requisito do modo ``json_schema`` estrito: ``additionalProperties: false`` e tudo obrigatório."""
    schema = Diagnosis.model_json_schema()
    objetos = [schema, *schema["$defs"].values()]
    for objeto in objetos:
        if objeto.get("type") == "object":
            assert objeto["additionalProperties"] is False
            assert set(objeto["required"]) == set(objeto["properties"])


@pytest.mark.parametrize("quantidade", [DIAGNOSIS_MIN_HYPOTHESES - 1, DIAGNOSIS_MAX_HYPOTHESES + 1])
def test_quantidade_de_hipoteses_fora_do_limite(quantidade: int) -> None:
    dados = _valid()
    base = dados["hypotheses"][0]
    dados["hypotheses"] = [{**copy.deepcopy(base), "id": f"H{i}"} for i in range(1, quantidade + 1)]
    dados["probable_conclusion"]["hypothesis_id"] = "H1"
    with pytest.raises(ValidationError):
        Diagnosis.model_validate(dados)


@pytest.mark.parametrize("valor", [-1, 101])
def test_probabilidade_fora_de_0_a_100(valor: int) -> None:
    dados = _valid()
    dados["hypotheses"][0]["probability_pct"] = valor
    with pytest.raises(ValidationError):
        Diagnosis.model_validate(dados)


def test_ids_de_hipotese_duplicados() -> None:
    dados = _valid()
    dados["hypotheses"][1]["id"] = "H1"
    with pytest.raises(ValidationError, match="únicos"):
        Diagnosis.model_validate(dados)


def test_conclusao_deve_apontar_para_hipotese_existente() -> None:
    dados = _valid()
    dados["probable_conclusion"]["hypothesis_id"] = "H9"
    with pytest.raises(ValidationError, match="hypothesis_id"):
        Diagnosis.model_validate(dados)


def test_confianca_invalida() -> None:
    dados = _valid()
    dados["probable_conclusion"]["confidence"] = "altíssima"
    with pytest.raises(ValidationError):
        Diagnosis.model_validate(dados)


def test_texto_vazio_e_recusado() -> None:
    dados = _valid()
    dados["customer_summary"] = "   "
    with pytest.raises(ValidationError):
        Diagnosis.model_validate(dados)
