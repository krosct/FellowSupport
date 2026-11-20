"""Histórico de execuções (PDF 4.4): lista com filtros e detalhe por id, sobre a porta ``RunRepo``.

Existe como serviço para a API, a CLI e a aba Histórico do site aplicarem **as mesmas regras** de filtro, ordem e
limite, sem cada adaptador reimplementá-las. A ordem é sempre "mais recente primeiro" (a do ``RunRepo``), e a
leitura é preguiçosa: o serviço para de abrir arquivos assim que junta ``limit`` execuções que casam.

O filtro por ``cache_key`` é o jeito de "localizar execuções equivalentes" (PDF 4.4): todas as execuções com a
mesma chave, com ou sem acerto de cache, inclusive as que terminaram em erro.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import islice

from app.domain.errors import ValidationFailed
from app.domain.models import ContentType, RunStatus
from app.ports.repositories import RunRepo, StoredRun

# Limites da listagem, definidos uma vez e usados por API, CLI e front (via /api/meta).
DEFAULT_HISTORY_LIMIT = 50
MAX_HISTORY_LIMIT = 500


@dataclass(frozen=True)
class HistoryFilters:
    """Filtros opcionais da listagem; um campo ``None`` não filtra.

    ``cache_key`` casa por **prefixo** (a CLI mostra só o começo da chave na tabela, e copiar o trecho basta).
    """

    customer_id: str | None = None
    ticket_id: str | None = None
    content_type: ContentType | None = None
    prompt_version: str | None = None
    status: RunStatus | None = None
    cache_key: str | None = None

    def matches(self, stored: StoredRun) -> bool:
        """``True`` se a execução satisfaz todos os filtros preenchidos."""
        run = stored.record
        checks = (
            (self.customer_id, run.customer_id),
            (self.ticket_id, run.ticket.id),
            (self.content_type, run.content_type),
            (self.prompt_version, run.prompt_version),
            (self.status, run.status),
        )
        if any(wanted is not None and wanted != actual for wanted, actual in checks):
            return False
        if self.cache_key:
            return bool(run.cache_key) and run.cache_key.startswith(self.cache_key.strip().lower())
        return True


def list_runs(
    runs: RunRepo, filters: HistoryFilters | None = None, limit: int = DEFAULT_HISTORY_LIMIT
) -> list[StoredRun]:
    """Execuções que casam com ``filters``, da mais recente para a mais antiga, no máximo ``limit``.

    Levanta ``ValidationFailed`` se ``limit`` estiver fora de 1 a ``MAX_HISTORY_LIMIT``: recusar em vez de
    "consertar" evita que um limite absurdo leia a pasta inteira sem o chamador perceber.
    """
    if not 1 <= limit <= MAX_HISTORY_LIMIT:
        raise ValidationFailed(f"O limite deve estar entre 1 e {MAX_HISTORY_LIMIT}.")
    filters = filters or HistoryFilters()
    matching = (stored for stored in runs.iter_recent() if filters.matches(stored))
    return list(islice(matching, limit))


def get_run(runs: RunRepo, run_id: str) -> StoredRun:
    """Execução pelo id. Levanta ``NotFound`` se não existir (o repositório valida o formato do id)."""
    return runs.get(run_id)
