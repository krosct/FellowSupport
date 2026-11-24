"""Comparação de versões de prompt no mesmo cenário (ADR 0021, 0031 e 0040).

Comparar **não gera** nada: compara execuções que já existem, uma por versão, escolhidas pelo usuário (no site, pelos
seletores da aba Comparar; na CLI, pelos ids). Gerar é uma ação à parte (``generate``). Casos de uso:

- ``load_comparable_runs``: lê as execuções e confere que dá para compará-las (justiça por código, ADR 0021);
- ``find_saved_comparison``: o cache das comparações (ADR 0038), para oferecer "carregar" ou "comparar de novo";
- ``save_comparison``: recebe as notas do candidato de **todas** as execuções (a avaliação começa do zero a cada
  comparação), grava as avaliações nas execuções, calcula o total por versão e o vencedor e salva
  ``var/comparisons/<id>.json``.

Cada comparação salva emite um evento ``evaluation`` por execução e um ``comparison`` com o resultado (ADR 0043).
"""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from app.domain import rubric
from app.domain.comparison import (
    COMPARISON_ID_LENGTH,
    CONCLUSION_BY_CANDIDATE,
    CONCLUSION_BY_SYSTEM,
    CONCLUSION_MAX_CHARS,
    ComparisonRecord,
    ComparisonScenario,
    ComparisonVersion,
    auto_conclusion,
    check_comparable,
    check_distinct,
    covers_runs,
    decide_winner,
    version_sort_key,
)
from app.domain.errors import ValidationFailed
from app.domain.evaluation import EVALUATOR_CANDIDATE, StoredEvaluation, parse_scores, total_score
from app.domain.models import ContentType
from app.ports.events import EVENT_COMPARISON, EVENT_EVALUATION, NULL_EVENT_LOG, EventLog
from app.ports.repositories import ComparisonRepo, RunRepo, StoredComparison, StoredRun
from app.services.clock import Clock, now_iso, system_clock
from app.services.evaluation import EvaluationContext, evaluation_event
from app.services.history import DEFAULT_HISTORY_LIMIT, MAX_HISTORY_LIMIT, Page, check_page_args, paginate

# Limites da listagem de comparações: os mesmos do histórico de execuções (SSOT em ``history``), com nome próprio
# para quem consome só as comparações.
DEFAULT_COMPARISONS_LIMIT = DEFAULT_HISTORY_LIMIT
MAX_COMPARISONS_LIMIT = MAX_HISTORY_LIMIT


@dataclass(frozen=True)
class ComparisonContext:
    """Dependências do salvamento da comparação, todas atrás de portas (ADR 0002)."""

    runs: RunRepo
    comparisons: ComparisonRepo
    evaluation: EvaluationContext
    timezone: str
    clock: Clock = field(default=system_clock)
    events: EventLog = field(default=NULL_EVENT_LOG, compare=False, repr=False)


def load_comparable_runs(runs: RunRepo, run_ids: Sequence[str]) -> list[StoredRun]:
    """Lê as execuções e confere que dá para compará-las (``check_comparable``), na ordem de ``run_ids``.

    ``NotFound`` se algum id não existir; ``ValidationFailed`` com o motivo nos demais casos.
    """
    check_distinct(run_ids, "execuções")  # antes de abrir arquivos: ids repetidos ou um só já bastam para recusar
    stored = [runs.get(run_id) for run_id in run_ids]
    check_comparable([item.record for item in stored])
    return stored


def save_comparison(
    ctx: ComparisonContext,
    *,
    run_ids: Sequence[str],
    evaluations: Mapping[str, object],
    conclusion: str | None = None,
) -> StoredComparison:
    """Salva a comparação das execuções ``run_ids`` e devolve o registro com o caminho do JSON.

    ``evaluations`` traz as notas do candidato por ``run_id``, **uma para cada execução**: cada comparação é avaliada
    do zero, mesmo que a execução já tenha nota de uma comparação anterior. Tudo é validado antes de qualquer escrita
    (notas, justiça, avaliação completa de cada lado), então um erro não deixa avaliações pela metade. Em seguida as
    notas são gravadas nas execuções, os totais somados, o vencedor decidido pelo maior total (empate = ``None``) e o
    arquivo gravado. ``conclusion`` é o texto do candidato (opcional); sem ele, vai o resumo automático dos totais.
    """
    # Valida ids enviados, tamanho da conclusão, justiça e notas antes de qualquer escrita.
    evaluations = dict(evaluations)
    unknown = sorted(set(evaluations) - set(run_ids))
    if unknown:
        raise ValidationFailed(f"Há avaliação para execuções fora da comparação: {', '.join(unknown)}.")
    text = (conclusion or "").strip()
    if len(text) > CONCLUSION_MAX_CHARS:
        raise ValidationFailed(f"A conclusão passa de {CONCLUSION_MAX_CHARS} caracteres.")

    stored = load_comparable_runs(ctx.runs, run_ids)
    evaluated_at = now_iso(ctx.clock, ctx.timezone)
    pending_evaluations: dict[str, dict] = {}
    for item in stored:
        record = item.record
        if record.run_id not in evaluations:
            raise ValidationFailed(
                f"A execução {record.run_id} ({record.prompt_version}) não tem avaliação: preencha as notas de "
                f"todos os {len(rubric.CRITERIA)} critérios."
            )
        parsed = parse_scores(evaluations[record.run_id])  # valida tudo antes de gravar qualquer coisa
        stored_eval = StoredEvaluation(**parsed.model_dump(), evaluator=EVALUATOR_CANDIDATE, evaluated_at=evaluated_at)
        pending_evaluations[record.run_id] = stored_eval.model_dump(mode="json")

    # Ordena versões, calcula totais do candidato, decide vencedor e grava PRIMEIRO o JSON da comparação.
    ordered = sorted(stored, key=lambda item: version_sort_key(item.record.prompt_version))  # v1, v2, v10
    totals = {item.record.prompt_version: total_score(pending_evaluations[item.record.run_id]) for item in ordered}
    winner = decide_winner(totals)
    first = ordered[0].record
    record = ComparisonRecord(
        comparison_id=uuid.uuid4().hex[:COMPARISON_ID_LENGTH],
        created_at=evaluated_at,
        scenario=ComparisonScenario(
            customer_id=first.customer_id,
            customer_profile=first.customer_profile,
            ticket=first.ticket,
            content_type=first.content_type,
            provider=first.provider,
            model=first.model,
            model_used=first.model_used,
            params=first.params,
        ),
        versions=[
            ComparisonVersion(
                prompt_version=item.record.prompt_version,
                run_id=item.record.run_id,
                run_path=item.saved_path,
                prompt_sha256=item.record.prompt_sha256,
                cache_hit=item.record.cache_hit,
                output=item.record.output,
                rendered=item.record.rendered,
                evaluation=pending_evaluations[item.record.run_id],
                total=totals[item.record.prompt_version],
            )
            for item in ordered
        ],
        winner=winner,
        conclusion=text or auto_conclusion(totals, winner),
        conclusion_source=CONCLUSION_BY_CANDIDATE if text else CONCLUSION_BY_SYSTEM,
    )
    saved_comparison_path = ctx.comparisons.save(record)

    # Só depois que a comparação está salva com segurança, grava as notas nos registros das execuções.
    for item in ordered:
        updated = item.record.model_copy(update={"evaluation": pending_evaluations[item.record.run_id]})
        ctx.runs.save(updated)
        ctx.events.emit(EVENT_EVALUATION, evaluation_event(
            updated, pending_evaluations[updated.run_id], comparison_id=record.comparison_id
        ))
    ctx.events.emit(EVENT_COMPARISON, {
        "comparison_id": record.comparison_id,
        "content_type": record.scenario.content_type.value,
        "customer_id": record.scenario.customer_id,
        "ticket_id": record.scenario.ticket.id,
        "provider": record.scenario.provider,
        "model": record.scenario.model,
        "model_used": record.scenario.model_used,
        "params": record.scenario.params.model_dump(mode="json"),
        "versions": [
            {"prompt_version": v.prompt_version, "run_id": v.run_id, "total": v.total, "cache_hit": v.cache_hit}
            for v in record.versions
        ],
        "winner": record.winner,
        "conclusion_source": record.conclusion_source,
        "conclusion": record.conclusion,
        "saved_path": saved_comparison_path,
    })
    return StoredComparison(record=record, saved_path=saved_comparison_path)


def list_comparisons(
    comparisons: ComparisonRepo, limit: int = DEFAULT_COMPARISONS_LIMIT, offset: int = 0
) -> Page[StoredComparison]:
    """Página de comparações salvas, da mais recente para a mais antiga, com o total (regras de ``paginate``)."""
    check_page_args(limit, offset)
    return paginate(comparisons.list_recent(), limit, offset)


def get_comparison(comparisons: ComparisonRepo, comparison_id: str) -> StoredComparison:
    """Comparação pelo id. Levanta ``NotFound`` se não existir (o repositório valida o formato do id)."""
    return comparisons.get(comparison_id)


def find_saved_comparison(comparisons: ComparisonRepo, run_ids: Sequence[str]) -> StoredComparison | None:
    """Cache das comparações (ADR 0038): a comparação mais recente já salva dessas execuções, ou ``None``.

    Aceita as mesmas entradas que o salvamento (2 ou mais execuções distintas) e não consulta o LLM nem as execuções:
    só os arquivos de ``var/comparisons/``. A listagem vem da mais recente para a mais antiga, então o primeiro
    registro que cobre as execuções é o mais novo.
    """
    check_distinct(run_ids, "execuções")
    return next((item for item in comparisons.list_recent() if covers_runs(item.record, run_ids)), None)


class ComparisonVersionSummary(BaseModel):
    """Versão e total de uma comparação, para a linha da listagem."""

    prompt_version: str
    total: int


class ComparisonSummary(BaseModel):
    """Linha da listagem de comparações: sem as saídas, que podem ser longas."""

    comparison_id: str
    created_at: str
    customer_name: str
    ticket_title: str
    content_type: ContentType
    versions: list[ComparisonVersionSummary] = Field(description="Versões e totais, na ordem da comparação.")
    winner: str | None
    saved_path: str


def summarize_comparison(stored: StoredComparison) -> ComparisonSummary:
    """Converte uma comparação lida do disco no resumo enxuto da listagem (compartilhado por API e CLI)."""
    record = stored.record
    return ComparisonSummary(
        comparison_id=record.comparison_id,
        created_at=record.created_at,
        customer_name=record.scenario.customer_profile.name,
        ticket_title=record.scenario.ticket.title,
        content_type=record.scenario.content_type,
        versions=[
            ComparisonVersionSummary(prompt_version=v.prompt_version, total=v.total)
            for v in record.versions
        ],
        winner=record.winner,
        saved_path=stored.saved_path,
    )
