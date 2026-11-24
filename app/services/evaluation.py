"""Avaliação manual das execuções pela rubrica (ADR 0020).

As notas oficiais são gravadas no campo ``evaluation`` do registro da execução. Regravar o registro usa
``RunRepo.save``, que é idempotente por ``run_id`` e ``timestamp`` (mesmo caminho, troca atômica do arquivo):
ninguém lê um JSON pela metade.

Cada avaliação gravada vira um evento ``evaluation`` no log de eventos (ADR 0043).
"""

from dataclasses import dataclass, field

from app.domain.evaluation import (
    EVALUATOR_CANDIDATE,
    StoredEvaluation,
    parse_scores,
    require_evaluable,
    total_score,
)
from app.domain.models import RunRecord
from app.ports.events import EVENT_EVALUATION, NULL_EVENT_LOG, EventLog
from app.ports.repositories import RunRepo, StoredRun
from app.services.clock import Clock, now_iso, system_clock


@dataclass(frozen=True)
class EvaluationContext:
    """Dependências da avaliação, todas atrás de portas (ADR 0002)."""

    runs: RunRepo
    timezone: str
    clock: Clock = field(default=system_clock)
    events: EventLog = field(default=NULL_EVENT_LOG, compare=False, repr=False)


def evaluation_event(record: RunRecord, evaluation: dict, *, comparison_id: str | None = None) -> dict:
    """Campos do evento ``evaluation``: a execução avaliada, as notas com as justificativas e o total.

    Compartilhado pela avaliação avulsa e pela comparação (que avalia cada execução dentro dela).
    """
    return {
        "run_id": record.run_id,
        "comparison_id": comparison_id,
        "content_type": record.content_type.value,
        "prompt_version": record.prompt_version,
        "prompt_sha256": record.prompt_sha256,
        "customer_id": record.customer_id,
        "ticket_id": record.ticket.id,
        "model_used": record.model_used,
        "total": total_score(evaluation),
        "evaluation": evaluation,
    }


def evaluate_manual(ctx: EvaluationContext, run_id: str, scores: object) -> StoredRun:
    """Grava a avaliação do candidato na execução ``run_id`` e devolve a execução já atualizada.

    ``scores`` é o objeto ``{critério: {score, justification}}``. Levanta ``NotFound`` se a execução não existe e
    ``ValidationFailed`` para execução com erro, nota fora de 1 a 5, justificativa vazia ou critério faltando.
    Reavaliar substitui a avaliação anterior.
    """
    # Carrega a execução, garante que deu certo, valida notas e regrava o JSON.
    stored = ctx.runs.get(run_id)
    require_evaluable(stored.record)
    parsed = parse_scores(scores)
    evaluation = StoredEvaluation(
        **parsed.model_dump(), evaluator=EVALUATOR_CANDIDATE, evaluated_at=now_iso(ctx.clock, ctx.timezone)
    )
    record = stored.record.model_copy(update={"evaluation": evaluation.model_dump(mode="json")})
    saved_path = ctx.runs.save(record)
    ctx.events.emit(EVENT_EVALUATION, evaluation_event(record, record.evaluation or {}))
    return StoredRun(record=record, saved_path=saved_path)
