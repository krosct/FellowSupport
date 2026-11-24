"""Evento da avaliação manual pela rubrica (ADR 0020).

A avaliação acontece só dentro da comparação (``app/services/comparison.py``), que grava as notas no campo
``evaluation`` de cada execução. Este módulo monta os campos do evento ``evaluation`` do log de eventos (ADR 0043),
emitido uma vez por execução avaliada.
"""

from app.domain.evaluation import total_score
from app.domain.models import RunRecord


def evaluation_event(record: RunRecord, evaluation: dict, *, comparison_id: str) -> dict:
    """Campos do evento ``evaluation``: a execução avaliada, as notas com as justificativas e o total."""
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
