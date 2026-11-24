"""Texto legível da CLI para cada tipo de conteúdo (adaptador de saída, sem regra de negócio).

Cada ``render_*`` recebe a saída já validada pelo schema e devolve o texto para o terminal. O fluxograma não é
desenhado aqui: usa o ASCII determinístico do domínio (``rendered`` do registro, ADR 0008).
"""

import textwrap
from collections.abc import Sequence

from app.domain import rubric
from app.domain.comparison import ComparisonRecord
from app.domain.evaluation import total_score
from app.domain.flow_render import render_flow
from app.domain.models import (
    ClarifyingQuestions,
    Confidence,
    ContentType,
    CustomerProfile,
    Diagnosis,
    FlowSummary,
    ResolutionSteps,
    RunRecord,
    Ticket,
)
from app.domain.prompting.registry import PromptDetail, PromptVersion
from app.ports.repositories import StoredComparison, StoredRun

# Largura de quebra de linha ao imprimir textos longos (ticket, diagnóstico, passos).
TEXT_WIDTH = 88

# Quantos caracteres do hash (SHA-256) mostrar na saída legível. Também é o tamanho do trecho da chave de cache
# na tabela do histórico (o filtro ``--cache-key`` aceita esse prefixo).
HASH_PREVIEW_CHARS = 12


def wrap(text: str, indent: str, marker: str = "") -> str:
    """Quebra ``text`` na largura da CLI; ``marker`` (ex.: ``"* "``) abre a 1ª linha e as demais alinham sob o texto."""
    return textwrap.fill(
        text, width=TEXT_WIDTH, initial_indent=indent + marker, subsequent_indent=indent + " " * len(marker)
    )




def render_diagnosis(diagnosis: Diagnosis) -> str:
    """Diagnóstico em texto legível para o terminal (hipóteses, evidências, faltantes, conclusão e resumo)."""
    # Formata hipóteses com evidências, lacunas, conclusão provável e resumo final.
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
    # Formata abertura, passos numerados com plano B, escalonamento e fechamento.
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
    # Formata perguntas em ordem de prioridade e indica se é possível avançar já.
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
    # Escolhe o renderizador correspondente ao tipo da execução validada.
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


def format_timestamp(timestamp: str) -> str:
    """``2026-11-20T14:03:11-03:00`` como ``2026-11-20 14:03:11``. O registro já está no fuso de APP_TIMEZONE
    (Brasília por padrão), então o deslocamento sai do texto sem converter nada."""
    return timestamp[:19].replace("T", " ")


def _scenario_lines(record: RunRecord) -> list[str]:
    """Cliente e ticket da execução (as linhas comuns a todas as versões de uma comparação)."""
    profile = record.customer_profile
    return [
        f"Cliente: {profile.name} ({profile.tech_level.value} · {profile.comm_style.value} · {profile.channel.value})",
        f"Ticket:  {record.ticket.title}",
    ]


def _version_lines(record: RunRecord) -> tuple[str, str, str]:
    """Execução, prompt e modelo: o que muda de uma execução para outra no mesmo cenário.

    Num acerto de cache mostra a origem em vez das tentativas (não houve chamada ao LLM).
    """
    model = f"Modelo:  {record.model_used or record.model} via {record.provider} · {record.latency_ms} ms"
    if record.cache_hit:
        model += f" · cache hit (origem {record.source_run_id}, sem chamar o LLM)"
    else:
        model += f" · tentativas: {record.attempts}"
    return (
        f"Execução: {record.run_id} · {format_timestamp(record.timestamp)}",
        f"Prompt:  {record.prompt_version} (sha256 {record.prompt_sha256[:HASH_PREVIEW_CHARS]})",
        model,
    )


def render_run_header(record: RunRecord) -> str:
    """Cabeçalho da execução: cliente, ticket, versão do prompt, modelo e latência."""
    run, prompt, model = _version_lines(record)
    return "\n".join([run, *_scenario_lines(record), prompt, model])


def render_scenario_header(record: RunRecord) -> str:
    """Cliente e ticket, uma vez só, no topo da comparação."""
    return "\n".join(_scenario_lines(record))


def render_version_header(record: RunRecord) -> str:
    """Execução, prompt e modelo de uma versão comparada (o cenário já foi mostrado no topo)."""
    return "\n".join(_version_lines(record))


# Espaço mínimo entre colunas nas tabelas da CLI.
_COLUMN_GAP = "  "


def render_table(headers: Sequence[str], rows: Sequence[Sequence[str]], min_widths: Sequence[int] = ()) -> str:
    """Formata cabeçalho e linhas com larguras adaptadas ao conteúdo de cada coluna.

    A última coluna não recebe preenchimento à direita para evitar espaços sobrando no fim da linha.
    """
    widths = [
        max(len(header), min_widths[i] if i < len(min_widths) else 0, *(len(row[i]) for row in rows))
        for i, header in enumerate(headers)
    ]

    def _format_row(cells: Sequence[str]) -> str:
        padded = [
            cell if i == len(cells) - 1 else f"{cell:<{widths[i]}}"
            for i, cell in enumerate(cells)
        ]
        return _COLUMN_GAP.join(padded).rstrip()

    return "\n".join([_format_row(headers), *(_format_row(row) for row in rows)])


def render_customers_table(customers: Sequence[CustomerProfile]) -> str:
    """Tabela legível de clientes com cabeçalho e colunas alinhadas."""
    if not customers:
        return "Nenhum cliente encontrado."
    rows = [(p.id, p.name, p.tech_level.value, p.comm_style.value, p.channel.value) for p in customers]
    return render_table(("ID", "NOME", "NÍVEL", "ESTILO", "CANAL"), rows)


def render_tickets_table(tickets: Sequence[Ticket]) -> str:
    """Tabela legível de tickets (id e título) com cabeçalho e colunas alinhadas."""
    if not tickets:
        return "Nenhum ticket encontrado."
    return render_table(("ID", "TÍTULO"), [(t.id, t.title) for t in tickets])


# Colunas da tabela do histórico: (título, largura mínima). Definidas uma vez para cabeçalho e linhas alinharem.
_HISTORY_COLUMNS = (
    ("ID", 12), ("QUANDO", 19), ("CLIENTE", 8), ("TICKET", 10), ("TIPO", 20),
    ("VER", 4), ("STATUS", 6), ("CACHE", 5), ("LATÊNCIA", 9), ("CHAVE", HASH_PREVIEW_CHARS),
)


def render_history_table(runs: Sequence[dict]) -> str:
    """Tabela legível das execuções (uma por linha), a partir dos resumos do histórico (``RunSummary``).

    Mostra o começo da chave de cache: copiá-lo em ``history generation --cache-key`` lista as execuções equivalentes.
    """
    # Imprime cabeçalho e linhas alinhadas com resumo e prefixo da chave de cache.
    if not runs:
        return "Nenhuma execução encontrada."
    rows = [
        (
            run["run_id"],
            format_timestamp(run["timestamp"]),
            run["customer_id"],
            run["ticket_id"],
            run["content_type"],
            run["prompt_version"],
            "erro" if run["status"] == "error" else "ok",
            "hit" if run["cache_hit"] else "-",
            f"{run['latency_ms']} ms",
            (run["cache_key"] or "-")[:HASH_PREVIEW_CHARS],
        )
        for run in runs
    ]
    headers = [title for title, _ in _HISTORY_COLUMNS]
    min_widths = [width for _, width in _HISTORY_COLUMNS]
    return render_table(headers, rows, min_widths)


def render_stored_run(stored: StoredRun) -> str:
    """Execução salva por inteiro, como o ``generate`` a mostra: cabeçalho, conteúdo (ou o erro) e o caminho.

    Reaproveita ``render_output``, o mesmo renderizador do ``generate``, para o ``show`` nunca divergir dele.
    """
    run = stored.record
    parts = [render_run_header(run), ""]
    if run.status == "ok":
        parts.append(render_output(run))
    else:
        parts.append(f"FALHOU: {run.error.message if run.error else 'erro desconhecido'}")
    parts += ["", f"JSON salvo em: {stored.saved_path}"]
    return "\n".join(parts)


def render_scale() -> str:
    """Escala da rubrica em uma linha (``1 = insuficiente, 2 = fraco, ...``), da fonte única ``rubric.py``."""
    return "Escala: " + ", ".join(f"{score} = {label}" for score, label in rubric.SCORE_LABELS.items())


def render_evaluation(title: str, evaluation: dict) -> str:
    """Notas de uma avaliação do candidato, uma por critério, com a justificativa e o total."""
    lines = [title]
    for criterion in rubric.CRITERIA:
        item = evaluation[criterion.key]
        lines.append(wrap(item["justification"], "     ", f"{criterion.label}: {item['score']} · "))
    lines.append(f"  Total: {total_score(evaluation)} de {rubric.TOTAL_MAX}")
    return "\n".join(lines)


def _versions_with_totals(record: ComparisonRecord) -> str:
    """``v1=9 v2=13``: versões e totais na ordem da comparação."""
    return " ".join(f"{v.prompt_version}={v.total}" for v in record.versions)


def render_comparison(stored: StoredComparison) -> str:
    """Comparação salva: cenário, avaliação e total por versão, vencedor e conclusão."""
    # Exibe cenário comum, avaliações de cada versão, vencedor e conclusão final.
    record = stored.record
    scenario = record.scenario
    profile = scenario.customer_profile
    lines = [
        f"Comparação: {record.comparison_id} · {format_timestamp(record.created_at)}",
        f"Cliente: {profile.name} ({profile.tech_level.value} · {profile.comm_style.value} · {profile.channel.value})",
        f"Ticket:  {scenario.ticket.title}",
        f"Tipo:    {scenario.content_type.label}",
        f"Modelo:  {scenario.model_used or scenario.model} via {scenario.provider}",
    ]
    for version in record.versions:
        lines += ["", f"VERSÃO {version.prompt_version} · execução {version.run_id}"]
        lines.append(render_evaluation("  Avaliação do candidato", version.evaluation))
    winner = f"versão {record.winner}" if record.winner else "empate (sem vencedor)"
    lines += [
        "",
        f"VENCEDOR: {winner} ({_versions_with_totals(record)}; máximo {rubric.TOTAL_MAX})",
        wrap(record.conclusion, "  ", f"Conclusão ({record.conclusion_source}): "),
        "",
        f"JSON salvo em: {stored.saved_path}",
    ]
    return "\n".join(lines)


# Colunas da tabela de comparações: (título, largura).
_COMPARISON_COLUMNS = (
    ("ID", 12), ("QUANDO", 19), ("CLIENTE", 14), ("TICKET", 24), ("TIPO", 20), ("TOTAIS", 24), ("VENCEDOR", 8),
)


def _fit(text: str, width: int) -> str:
    """Corta o texto na largura da coluna, com reticências."""
    return text if len(text) <= width else f"{text[: width - 1]}…"


def render_comparisons_table(items: Sequence[dict]) -> str:
    """Tabela legível das comparações (``ComparisonSummary``), da mais recente para a mais antiga."""
    if not items:
        return "Nenhuma comparação encontrada."
    rows = [
        tuple(
            _fit(cell, width)
            for cell, (_, width) in zip(
                (
                    item["comparison_id"],
                    format_timestamp(item["created_at"]),
                    item["customer_name"],
                    item["ticket_title"],
                    item["content_type"],
                    " ".join(f"{v['prompt_version']}={v['total']}" for v in item["versions"]),
                    item["winner"] or "empate",
                ),
                _COMPARISON_COLUMNS,
                strict=True,
            )
        )
        for item in items
    ]
    headers = [title for title, _ in _COMPARISON_COLUMNS]
    min_widths = [width for _, width in _COMPARISON_COLUMNS]
    return render_table(headers, rows, min_widths)


def render_page_info(page: int, limit: int, total: int, singular: str, plural: str) -> str:
    """Rodapé da listagem paginada, como no site: ``Página 1 de 3 · 57 execuções (20 por página)``."""
    pages = max(1, -(-total // limit))
    noun = singular if total == 1 else plural
    return f"Página {page} de {pages} · {total} {noun} ({limit} por página)"


def render_versions(versions: Sequence[PromptVersion], default: str | None, *, details: bool = False) -> str:
    """Versões de prompt com base, hash e descrição; com ``details=True``, inclui o que mudou nas derivadas."""
    if not versions:
        return "Nenhuma versão encontrada."
    rows = [
        (
            v.version,
            v.based_on or "-",
            v.content_sha256[:HASH_PREVIEW_CHARS],
            f"{v.description}{' (padrão)' if v.version == default else ''}",
        )
        for v in versions
    ]
    table = render_table(("VERSÃO", "BASE", "HASH", "DESCRIÇÃO"), rows, (6, 4, HASH_PREVIEW_CHARS))
    if not details:
        return table
    changes = render_version_changes(versions)
    return table + (f"\n\n{changes}" if changes else "")


def render_prompt_detail(detail: PromptDetail, *, is_default: bool = False) -> str:
    """Detalhes completos de uma versão de prompt: metadados, mudanças e lista de arquivos."""
    tag = " (padrão)" if is_default else ""
    base = detail.based_on or "- (linha de base)"
    lines = [
        f"Versão:    {detail.version}{tag}",
        f"Base:      {base}",
        f"Criado em: {detail.created}",
        f"Hash:      {detail.content_sha256[:HASH_PREVIEW_CHARS]}",
        wrap(detail.description, "", "Descrição: "),
    ]
    if detail.changes:
        lines.append("")
        lines.append(f"Mudanças ({len(detail.changes)}):")
        for change in detail.changes:
            lines.append(wrap(change.what, "  ", "- "))
            lines.append(wrap(change.why, "    ", "Por quê: "))
            lines.append(wrap(change.expected_effect, "    ", "Efeito esperado: "))
    lines.append("")
    lines.append(f"Arquivos ({len(detail.files)}): {', '.join(sorted(detail.files))}")
    return "\n".join(lines)


def render_version_changes(versions: Sequence[PromptVersion]) -> str:
    """O que mudou em cada versão derivada (``changes`` do ``meta.json``): o quê, por quê e efeito esperado.

    Só as versões com ``based_on`` aparecem (a linha de base não tem com o que comparar); vazio se não houver nenhuma.
    """
    blocks = []
    for version in (v for v in versions if v.based_on):
        lines = [f"O que mudou na {version.version} em relação à {version.based_on} ({len(version.changes)})"]
        for change in version.changes:
            lines.append(wrap(change.what, "  ", "- "))
            lines.append(wrap(change.why, "    ", "Por quê: "))
            lines.append(wrap(change.expected_effect, "    ", "Efeito esperado: "))
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def render_meta(meta: dict) -> str:
    """Metadados do app (``AppMeta``) em texto: provedor, versão padrão, tipos, rubrica."""
    limits = meta["limits"]
    rub = meta["rubric"]

    def _labels(options: list[dict]) -> str:
        """``valor (Rótulo)``; só o valor quando o rótulo é o próprio valor com maiúscula."""
        return ", ".join(
            item["value"] if item["value"] == item["label"].lower() else f"{item['value']} ({item['label']})"
            for item in options
        )

    scale = ", ".join(f"{score} = {label}" for score, label in rub["scale"]["labels"].items())
    lines = [
        f"Provedor:          {meta['llm']['provider']} · modelo {meta['llm']['model']}",
        f"Versão padrão:     {meta['default_prompt_version']}",
        f"Tipos de conteúdo: {_labels(meta['content_types'])}; {meta['all_option']['value']} gera os quatro",
        f"Nível técnico:     {_labels(meta['enums']['tech_level'])}",
        f"Estilo:            {_labels(meta['enums']['comm_style'])}",
        f"Canal:             {_labels(meta['enums']['channel'])}",
        f"Confiança:         {_labels(meta['confidence_levels'])}",
        "",
        f"Rubrica (total máximo {rub['total_max']}; {scale}):",
        *(f"  {c['label']}: {c['description']}" for c in rub["criteria"]),
        "",
        "Limites:",
        f"  ticket: título até {limits['max_ticket_title_chars']} e corpo até {limits['max_ticket_chars']} caracteres",
        f"  nome do cliente até {limits['max_profile_name_chars']} caracteres",
        f"  itens por página: {', '.join(map(str, limits['page_sizes']))} (padrão {limits['history_limit']})",
        f"  comparação: ao menos {limits['min_compared_versions']} versões; conclusão até "
        f"{limits['conclusion_max_chars']} caracteres",
    ]
    return "\n".join(lines)
