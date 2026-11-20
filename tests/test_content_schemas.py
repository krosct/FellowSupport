"""Testes dos schemas ``ResolutionSteps``, ``ClarifyingQuestions`` e ``FlowSummary`` e das regras de canal."""

from __future__ import annotations

import copy

import pytest
from pydantic import ValidationError

from app.domain.channel_rules import CHANNEL_FORMAT_RULES, find_channel_violations
from app.domain.models import (
    QUESTIONS_MAX,
    QUESTIONS_MIN,
    STEPS_MAX,
    STEPS_MIN,
    Channel,
    ClarifyingQuestions,
    FlowSummary,
    ResolutionSteps,
)


def _step(n: int) -> dict:
    return {"order": n, "title": f"Passo {n}", "instruction": "Faça isto.", "expected_result": "Vê aquilo.",
            "if_it_fails": "Tente de novo."}


def _steps(n: int = 3) -> dict:
    return {"opening": "Vamos resolver.", "steps": [_step(i) for i in range(1, n + 1)],
            "when_to_escalate": "Se nada funcionar.", "closing": "Aguardo seu retorno."}


def _question(n: int) -> dict:
    return {"priority": n, "question": f"Pergunta {n}?", "why_it_matters": "Muda a causa.", "unlocks": "H1"}


def _questions(n: int = 3) -> dict:
    return {"questions": [_question(i) for i in range(1, n + 1)], "can_proceed_without_answers": False,
            "proceed_note": "Sem as respostas não dá para decidir."}


def _flow() -> dict:
    return {
        "nodes": [
            {"id": "n1", "type": "start", "label": "SMS não chega"},
            {"id": "n2", "type": "decision", "label": "Número correto?"},
            {"id": "n3", "type": "action", "label": "Corrigir o cadastro"},
            {"id": "n4", "type": "end", "label": "Resolvido"},
        ],
        "edges": [
            {"source": "n1", "target": "n2", "label": ""},
            {"source": "n2", "target": "n3", "label": "Não"},
            {"source": "n2", "target": "n4", "label": "Sim"},
            {"source": "n3", "target": "n4", "label": ""},
        ],
    }


# --- ResolutionSteps ------------------------------------------------------------------------------


def test_passos_validos() -> None:
    assert len(ResolutionSteps.model_validate(_steps()).steps) == 3


@pytest.mark.parametrize("n", [STEPS_MIN - 1, STEPS_MAX + 1])
def test_quantidade_de_passos_fora_do_limite(n: int) -> None:
    with pytest.raises(ValidationError):
        ResolutionSteps.model_validate(_steps(n))


@pytest.mark.parametrize("orders", [[1, 1, 3], [2, 3, 4], [1, 3, 2]])
def test_ordem_dos_passos_deve_ser_sequencial(orders: list[int]) -> None:
    data = _steps()
    for step, order in zip(data["steps"], orders, strict=True):
        step["order"] = order
    with pytest.raises(ValidationError, match="order"):
        ResolutionSteps.model_validate(data)


@pytest.mark.parametrize("campo", ["opening", "when_to_escalate", "closing"])
def test_passos_exigem_abertura_escalonamento_e_fechamento(campo: str) -> None:
    data = _steps()
    data[campo] = "  "
    with pytest.raises(ValidationError):
        ResolutionSteps.model_validate(data)


@pytest.mark.parametrize("campo", ["title", "instruction", "expected_result", "if_it_fails"])
def test_cada_passo_exige_resultado_esperado_e_plano_b(campo: str) -> None:
    data = _steps()
    del data["steps"][0][campo]
    with pytest.raises(ValidationError, match=campo):
        ResolutionSteps.model_validate(data)


def test_passos_recusam_campo_extra() -> None:
    data = _steps()
    data["raciocinio"] = "..."
    with pytest.raises(ValidationError):
        ResolutionSteps.model_validate(data)


# --- ClarifyingQuestions --------------------------------------------------------------------------


@pytest.mark.parametrize("n", range(QUESTIONS_MIN, QUESTIONS_MAX + 1))
def test_de_3_a_5_perguntas_sao_aceitas(n: int) -> None:
    assert len(ClarifyingQuestions.model_validate(_questions(n)).questions) == n


@pytest.mark.parametrize("n", [0, 2, 6])
def test_menos_de_3_ou_mais_de_5_perguntas_sao_recusadas(n: int) -> None:
    with pytest.raises(ValidationError):
        ClarifyingQuestions.model_validate(_questions(n))


def test_prioridades_devem_ser_sequenciais() -> None:
    data = _questions(3)
    data["questions"][1]["priority"] = 1
    with pytest.raises(ValidationError, match="priority"):
        ClarifyingQuestions.model_validate(data)


def test_perguntas_exigem_motivo_e_o_que_destravam() -> None:
    for campo in ("why_it_matters", "unlocks"):
        data = _questions(3)
        del data["questions"][0][campo]
        with pytest.raises(ValidationError, match=campo):
            ClarifyingQuestions.model_validate(data)


def test_perguntas_exigem_o_campo_de_avancar_sem_respostas() -> None:
    data = _questions(3)
    del data["can_proceed_without_answers"]
    with pytest.raises(ValidationError, match="can_proceed_without_answers"):
        ClarifyingQuestions.model_validate(data)


# --- FlowSummary ----------------------------------------------------------------------------------


def test_fluxo_valido() -> None:
    assert len(FlowSummary.model_validate(_flow()).nodes) == 4


def _mutar(fn) -> dict:
    data = copy.deepcopy(_flow())
    fn(data)
    return data


@pytest.mark.parametrize(
    ("mutacao", "trecho"),
    [
        (lambda d: d["nodes"][2].update(id="n1"), "únicos"),
        (lambda d: d["nodes"][3].update(type="action"), "ao menos um nó end"),
        (lambda d: d["nodes"][2].update(type="start"), "exatamente um nó start"),
        (lambda d: d["nodes"][0].update(type="action"), "exatamente um nó start"),
        (lambda d: d["edges"][1].update(target="n9"), "destino inexistente"),
        (lambda d: d["edges"][0].update(source="n0"), "origem inexistente"),
        (lambda d: d["edges"][3].update(target="n3"), "para ele mesmo"),
        (lambda d: d["edges"].append({"source": "n4", "target": "n3", "label": ""}), "end"),
        (lambda d: d["edges"].append({"source": "n3", "target": "n2", "label": ""}), "exatamente 1 aresta"),
        (lambda d: d["edges"][1].update(label=""), "rótulo"),
        (lambda d: d["edges"][2].update(label="Não"), "rótulos diferentes"),
    ],
)
def test_fluxo_invalido_e_rejeitado(mutacao, trecho: str) -> None:
    with pytest.raises(ValidationError, match=trecho):
        FlowSummary.model_validate(_mutar(mutacao))


def test_start_nao_recebe_arestas() -> None:
    data = _flow()
    data["nodes"].insert(1, {"id": "n5", "type": "action", "label": "Volta"})
    data["edges"] = [
        {"source": "n1", "target": "n2", "label": ""},
        {"source": "n2", "target": "n5", "label": "Não"},
        {"source": "n2", "target": "n4", "label": "Sim"},
        {"source": "n5", "target": "n1", "label": ""},
        {"source": "n3", "target": "n4", "label": ""},
    ]
    with pytest.raises(ValidationError, match="start não pode receber"):
        FlowSummary.model_validate(data)


def test_ciclo_e_rejeitado() -> None:
    data = {
        "nodes": [
            {"id": "a", "type": "start", "label": "Início"},
            {"id": "b", "type": "action", "label": "Tentar"},
            {"id": "c", "type": "decision", "label": "Deu certo?"},
            {"id": "d", "type": "end", "label": "Fim"},
        ],
        "edges": [
            {"source": "a", "target": "b", "label": ""},
            {"source": "b", "target": "c", "label": ""},
            {"source": "c", "target": "b", "label": "Não"},
            {"source": "c", "target": "d", "label": "Sim"},
        ],
    }
    with pytest.raises(ValidationError, match="ciclo"):
        FlowSummary.model_validate(data)


def test_no_inalcancavel_e_rejeitado() -> None:
    data = _flow()
    data["nodes"].append({"id": "n5", "type": "end", "label": "Órfão"})  # ninguém aponta para ele
    with pytest.raises(ValidationError, match="não alcançáveis"):
        FlowSummary.model_validate(data)


def test_convergencia_e_aceita() -> None:
    """Dois ramos podem chegar ao mesmo nó (grafo acíclico, não só árvore)."""
    assert FlowSummary.model_validate(_flow())  # n2 -Sim-> n4 e n3 -> n4


# --- regras por canal -----------------------------------------------------------------------------


def test_todo_canal_tem_instrucao() -> None:
    assert set(CHANNEL_FORMAT_RULES) == set(Channel)


@pytest.mark.parametrize("texto", ["**negrito**", "- item", "1. passo", "# Título", "use `cmd`", "[a](http://x)"])
def test_telefone_recusa_markdown(texto: str) -> None:
    data = _steps()
    data["opening"] = texto
    problema = find_channel_violations(Channel.TELEFONE, ResolutionSteps.model_validate(data))
    assert "telefone" in problema and "markdown" in problema


def test_telefone_aceita_texto_corrido_e_outros_canais_aceitam_markdown() -> None:
    limpo = ResolutionSteps.model_validate(_steps())
    assert find_channel_violations(Channel.TELEFONE, limpo) == ""
    data = _steps()
    data["opening"] = "**Olá**"
    com_md = ResolutionSteps.model_validate(data)
    assert find_channel_violations(Channel.CHAT, com_md) == ""
    assert find_channel_violations(Channel.EMAIL, com_md) == ""


def test_telefone_verifica_perguntas_e_fluxo() -> None:
    q = _questions(3)
    q["questions"][2]["question"] = "- Qual o modelo?"
    assert find_channel_violations(Channel.TELEFONE, ClarifyingQuestions.model_validate(q))
    f = _flow()
    f["nodes"][2]["label"] = "Corrigir **agora**"
    assert find_channel_violations(Channel.TELEFONE, FlowSummary.model_validate(f))
