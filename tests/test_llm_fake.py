"""Testes do provedor fake e dos auxiliares de saída de LLM."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from app.adapters.llm.fake import FAKE_MODEL_NAME, FakeLLM
from app.domain.channel_rules import find_channel_violations
from app.domain.errors import ValidationFailed
from app.domain.flow_render import render_flow
from app.domain.llm_output import extract_json_object, format_validation_error
from app.domain.models import (
    OUTPUT_SCHEMAS,
    Channel,
    ClarifyingQuestions,
    ContentType,
    Diagnosis,
    FlowSummary,
    ResolutionSteps,
)
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


@pytest.mark.parametrize("tipo", list(ContentType))
def test_fake_devolve_resposta_valida_para_os_quatro_schemas(tipo: ContentType) -> None:
    schema = OUTPUT_SCHEMAS[tipo]
    r = FakeLLM().complete(_mensagens("O SMS não chega"), schema, PARAMS)
    saida = schema.model_validate(r.parsed)
    # Válida para qualquer canal: sem markdown, então serve também ao telefone.
    for canal in Channel:
        assert find_channel_violations(canal, saida) == ""
    assert r.text == FakeLLM().complete(_mensagens("O SMS não chega"), schema, PARAMS).text  # determinística


def test_fake_do_fluxo_desenha_com_ramo_e_convergencia() -> None:
    fluxo = FlowSummary.model_validate(FakeLLM().complete(_mensagens("x"), FlowSummary, PARAMS).parsed)
    ascii_ = render_flow(fluxo)
    assert "├─ Sim ─▶" in ascii_ and "└─ Não ─▶" in ascii_ and "(segue em" in ascii_


def test_fake_das_perguntas_e_dos_passos_respeitam_os_limites() -> None:
    perguntas = ClarifyingQuestions.model_validate(
        FakeLLM().complete(_mensagens("x"), ClarifyingQuestions, PARAMS).parsed
    )
    assert 3 <= len(perguntas.questions) <= 5
    passos = ResolutionSteps.model_validate(FakeLLM().complete(_mensagens("x"), ResolutionSteps, PARAMS).parsed)
    assert all(p.expected_result and p.if_it_fails for p in passos.steps)


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
        # Chaves soltas na prosa antes ou depois do JSON não atrapalham.
        ('Use o formato {chave: valor}. Resposta: {"a": 1} Fim {assim}.', {"a": 1}),
        ('Pensando... {"a": {"b": 2}} e mais {x}', {"a": {"b": 2}}),
        # Chaves e aspas dentro de strings do JSON não confundem a contagem.
        ('Aqui: {"a": "texto com } e { e \\" aspa", "b": 2} ok', {"a": 'texto com } e { e " aspa', "b": 2}),
        # Resposta truncada com objeto interno completo não devolve o interno como se fosse a resposta.
        ('{"a": {"b": 2}, "c": ', None),
        ('Segue: {"a": {"b": 2}', None),
        ("```json\n{\"a\": 1}\n``` e {outra}", {"a": 1}),
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
