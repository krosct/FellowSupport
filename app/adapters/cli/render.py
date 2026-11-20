"""Texto legível da CLI para cada tipo de conteúdo (adaptador de saída, sem regra de negócio).

Cada ``render_*`` recebe a saída já validada pelo schema e devolve o texto para o terminal. O fluxograma não é
desenhado aqui: usa o ASCII determinístico do domínio (``rendered`` do registro, ADR 0008).
"""

from __future__ import annotations

import textwrap

from app.domain.flow_render import render_flow
from app.domain.models import (
    ClarifyingQuestions,
    Confidence,
    ContentType,
    Diagnosis,
    FlowSummary,
    ResolutionSteps,
    RunRecord,
)

# Largura de quebra de linha ao imprimir textos longos (ticket, diagnóstico, passos).
TEXT_WIDTH = 88

# Quantos caracteres do hash (SHA-256) mostrar na saída legível.
HASH_PREVIEW_CHARS = 12


def wrap(text: str, indent: str, marker: str = "") -> str:
    """Quebra ``text`` na largura da CLI; ``marker`` (ex.: ``"* "``) abre a 1ª linha e as demais alinham sob o texto."""
    return textwrap.fill(
        text, width=TEXT_WIDTH, initial_indent=indent + marker, subsequent_indent=indent + " " * len(marker)
    )




def render_diagnosis(diagnosis: Diagnosis) -> str:
    """Diagnóstico em texto legível para o terminal (hipóteses, evidências, faltantes, conclusão e resumo)."""
    lines = ["HIPÓTESES"]
    for h in diagnosis.hypotheses:
        lines.append(wrap(f"{h.description} ({h.probability_pct}%)", "  ", f"{h.id} · "))
        lines += [wrap(text, "      ", "+ ") for text in h.evidence_for]
        lines += [wrap(text, "      ", "- ") for text in h.evidence_against]
    lines += ["", "EVIDÊNCIAS DISPONÍVEIS"] + [wrap(text, "  ", "* ") for text in diagnosis.available_evidence]
    lines += ["", "INFORMAÇÕES FALTANTES"]
    lines += [wrap(f"{info.item}: {info.why_it_matters}", "  ", "* ") for info in diagnosis.missing_information]
    conclusion = diagnosis.probable_conclusion
    confidence = Confidence(conclusion.confidence).label
    lines += ["", f"CONCLUSÃO PROVÁVEL (confiança: {confidence})"]
    lines.append(wrap(conclusion.summary, "  ", f"{conclusion.hypothesis_id} · "))
    lines += ["", "RESUMO PARA O CLIENTE", wrap(diagnosis.customer_summary, "  ")]
    return "\n".join(lines)


def render_resolution_steps(steps: ResolutionSteps) -> str:
    """Passo a passo em texto: abertura, passos numerados (resultado esperado e plano B), escalonamento e fim."""
    lines = ["ABERTURA", wrap(steps.opening, "  "), "", "PASSOS"]
    for step in steps.steps:
        lines.append(wrap(step.title, "  ", f"{step.order}. "))
        lines.append(wrap(step.instruction, "     "))
        lines.append(wrap(step.expected_result, "     ", "Esperado: "))
        lines.append(wrap(step.if_it_fails, "     ", "Se falhar: "))
    lines += ["", "QUANDO ESCALAR", wrap(steps.when_to_escalate, "  "), "", "FECHAMENTO", wrap(steps.closing, "  ")]
    return "\n".join(lines)


def render_clarifying_questions(questions: ClarifyingQuestions) -> str:
    """Perguntas por ordem de prioridade, cada uma com o motivo e o que destrava, e o veredito de avanço."""
    lines = ["PERGUNTAS (da mais para a menos prioritária)"]
    for item in questions.questions:
        lines.append(wrap(item.question, "  ", f"{item.priority}. "))
        lines.append(wrap(item.why_it_matters, "     ", "Motivo: "))
        lines.append(wrap(item.unlocks, "     ", "Destrava: "))
    verdict = "SIM" if questions.can_proceed_without_answers else "NÃO"
    lines += ["", f"DÁ PARA AVANÇAR SEM AS RESPOSTAS? {verdict}", wrap(questions.proceed_note, "  ")]
    return "\n".join(lines)


def render_flow_summary(flow: FlowSummary, rendered: str | None) -> str:
    """Fluxograma ASCII: usa o desenho gravado na execução ou, na falta dele, desenha de novo (é puro)."""
    return rendered or render_flow(flow)


def render_output(record: RunRecord) -> str:
    """Texto do conteúdo da execução, conforme o tipo. Exige ``record.output`` válido (execução com sucesso)."""
    output = record.output or {}
    match record.content_type:
        case ContentType.DIAGNOSIS:
            return render_diagnosis(Diagnosis.model_validate(output))
        case ContentType.RESOLUTION_STEPS:
            return render_resolution_steps(ResolutionSteps.model_validate(output))
        case ContentType.CLARIFYING_QUESTIONS:
            return render_clarifying_questions(ClarifyingQuestions.model_validate(output))
        case ContentType.FLOW_SUMMARY:
            return render_flow_summary(FlowSummary.model_validate(output), record.rendered)


def render_run_header(record: RunRecord) -> str:
    """Cabeçalho da execução: cliente, ticket, versão do prompt, modelo e latência.

    Num acerto de cache mostra a origem em vez das tentativas (não houve chamada ao LLM).
    """
    profile = record.customer_profile
    model = f"Modelo:  {record.model_used or record.model} via {record.provider} · {record.latency_ms} ms"
    if record.cache_hit:
        model += f" · cache hit (origem {record.source_run_id}, sem chamar o LLM)"
    else:
        model += f" · tentativas: {record.attempts}"
    return "\n".join([
        f"Cliente: {profile.name} ({profile.tech_level.value} · {profile.comm_style.value} · {profile.channel.value})",
        f"Ticket:  {record.ticket.title}",
        f"Prompt:  {record.prompt_version} (sha256 {record.prompt_sha256[:HASH_PREVIEW_CHARS]})",
        model,
    ])
