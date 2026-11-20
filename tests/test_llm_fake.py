"""Testes do provedor fake e dos auxiliares de saída de LLM."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from app.adapters.llm.fake import FAKE_MODEL_NAME, FakeLLM
from app.domain.errors import ValidationFailed
from app.domain.llm_output import extract_json_object, format_validation_error
from app.domain.models import Diagnosis
from app.ports.llm import LLMParams

PARAMS = LLMParams(model="qualquer/modelo", temperature=0.1, max_tokens=100, structured_mode="json_schema")


def _mensagens(ticket: str) -> list[dict]:
    return [
        {"role": "system", "content": "persona"},
        {"role": "user", "content": f"<ticket>\n{ticket}\n</ticket>"},
    ]


def test_fake_devolve_diagnostico_valido_pelo_schema() -> None:
    r = FakeLLM().complete(_mensagens("O SMS não chega"), Diagnosis, PARAMS)
    diagnostico = Diagnosis.model_validate(r.parsed)
    assert len(diagnostico.hypotheses) >= 2
    assert r.model_used == FAKE_MODEL_NAME
    assert r.usage["prompt_tokens"] > 0 and r.usage["completion_tokens"] > 0
    assert "simulada" in diagnostico.customer_summary


def test_fake_e_deterministico_e_cita_o_ticket() -> None:
    a = FakeLLM().complete(_mensagens("O SMS não chega"), Diagnosis, PARAMS)
    b = FakeLLM().complete(_mensagens("O SMS não chega"), Diagnosis, PARAMS)
    c = FakeLLM().complete(_mensagens("Dashboard lento"), Diagnosis, PARAMS)
    assert a.text == b.text
    assert "O SMS não chega" in a.text and "O SMS não chega" not in c.text


def test_fake_sem_tags_de_ticket_usa_texto_generico() -> None:
    r = FakeLLM().complete([{"role": "user", "content": "oi"}], Diagnosis, PARAMS)
    assert Diagnosis.model_validate(r.parsed)


def test_fake_recusa_schema_sem_simulacao() -> None:
    class Outro(BaseModel):
        x: int

    with pytest.raises(ValidationFailed, match="Outro"):
        FakeLLM().complete(_mensagens("x"), Outro, PARAMS)


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ('{"a": 1}', {"a": 1}),
        ('```json\n{"a": 1}\n```', {"a": 1}),
        ('Claro! Aqui está:\n{"a": {"b": 2}}\nEspero ter ajudado.', {"a": {"b": 2}}),
        ("sem json nenhum", None),
        ("[1, 2, 3]", None),
        ('{"truncado": ', None),
        ("", None),
    ],
)
def test_extract_json_object(texto: str, esperado: dict | None) -> None:
    assert extract_json_object(texto) == esperado


def test_format_validation_error_lista_campos_sem_eco_do_valor() -> None:
    with pytest.raises(ValidationError) as exc:
        Diagnosis.model_validate({"hypotheses": "SEGREDO-NO-VALOR"})
    texto = format_validation_error(exc.value)
    assert "- hypotheses:" in texto
    assert "SEGREDO-NO-VALOR" not in texto
