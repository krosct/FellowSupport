"""Histórico de execuções: lista com filtros e detalhe por id, sobre a porta ``RunRepo``.

Existe como serviço para a API, a CLI e a aba Histórico do site aplicarem **as mesmas regras** de filtro, ordem e
paginação, sem cada adaptador reimplementá-las. A ordem é sempre "mais recente primeiro" (a do ``RunRepo``). A
listagem devolve uma página (``limit`` itens a partir de ``offset``) e o total que casa com os filtros, para o site e
a CLI mostrarem "página X de Y"; contar o total exige ler todas as execuções que casam.

O filtro por ``cache_key`` é o jeito de "localizar execuções equivalentes": todas as execuções com a
mesma chave, com ou sem acerto de cache, inclusive as que terminaram em erro.
"""

import math
from collections.abc import Iterable
from dataclasses import dataclass

from pydantic import BaseModel

from app.domain.errors import ValidationFailed
from app.domain.evaluation import total_score
from app.domain.models import ContentType, RunError, RunStatus
from app.ports.repositories import RunRepo, StoredRun

# Limites da listagem, definidos uma vez e usados por API, CLI e front (via /api/meta).
DEFAULT_HISTORY_LIMIT = 50
MAX_HISTORY_LIMIT = 500
# Itens por página oferecidos no site (seletor) e na CLI (``--limit``) para o histórico e as comparações.
PAGE_SIZES = (10, 20, 50, 100)


class RunSummary(BaseModel):
    """Linha da listagem do histórico: o suficiente para a tabela, sem a saída nem as mensagens enviadas."""

    run_id: str
    timestamp: str
    status: RunStatus
    customer_id: str
    customer_name: str
    ticket_id: str
    ticket_title: str
    content_type: ContentType
    prompt_version: str
    provider: str
    model: str
    model_used: str | None
    cache_key: str | None
    cache_hit: bool
    source_run_id: str | None
    attempts: int
    latency_ms: int
    error: RunError | None
    evaluation_total: int | None
    saved_path: str


def summarize_run(stored: StoredRun) -> RunSummary:
    """Converte uma execução lida do disco na linha enxuta da listagem (compartilhado por API e CLI)."""
    run = stored.record
    return RunSummary(
        run_id=run.run_id,
        timestamp=run.timestamp,
        status=run.status,
        customer_id=run.customer_id,
        customer_name=run.customer_profile.name,
        ticket_id=run.ticket.id,
        ticket_title=run.ticket.title,
        content_type=run.content_type,
        prompt_version=run.prompt_version,
        provider=run.provider,
        model=run.model,
        model_used=run.model_used,
        cache_key=run.cache_key,
        cache_hit=run.cache_hit,
        source_run_id=run.source_run_id,
        attempts=run.attempts,
        latency_ms=run.latency_ms,
        error=run.error,
        evaluation_total=total_score(run.evaluation) if run.evaluation else None,
        saved_path=stored.saved_path,
    )


@dataclass(frozen=True)
class Page[T]:
    """Uma página da listagem: os itens pedidos e o total que casa com os filtros (em todas as páginas)."""

    items: list[T]
    total: int
    limit: int
    offset: int

    @property
    def page(self) -> int:
        """Número da página (a partir de 1) que ``offset`` e ``limit`` descrevem."""
        return self.offset // self.limit + 1

    @property
    def pages(self) -> int:
        """Quantidade de páginas (ao menos 1, mesmo sem itens)."""
        return max(1, math.ceil(self.total / self.limit))


def check_page_args(limit: int, offset: int) -> None:
    """Recusa ``limit`` fora de 1 a ``MAX_HISTORY_LIMIT`` e ``offset`` negativo (``ValidationFailed``).

    Recusar em vez de "consertar" evita que um limite absurdo leia e devolva a pasta inteira sem o chamador perceber.
    """
    if not 1 <= limit <= MAX_HISTORY_LIMIT:
        raise ValidationFailed(f"O limite deve estar entre 1 e {MAX_HISTORY_LIMIT}.")
    if offset < 0:
        raise ValidationFailed("O deslocamento (offset) não pode ser negativo.")


def paginate[T](items: Iterable[T], limit: int, offset: int) -> Page[T]:
    """Corta ``items`` (já filtrados e ordenados) na página pedida e conta o total."""
    check_page_args(limit, offset)
    chosen: list[T] = []
    total = 0
    for item in items:
        if offset <= total < offset + limit:
            chosen.append(item)
        total += 1
    return Page(items=chosen, total=total, limit=limit, offset=offset)


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
        # Compara cada campo exato preenchido no filtro com o registro da execução.
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
        # Aceita busca por prefixo da chave de cache (como exibido na tabela da CLI).
        if self.cache_key:
            return bool(run.cache_key) and run.cache_key.startswith(self.cache_key.strip().lower())
        return True


def list_runs(
    runs: RunRepo, filters: HistoryFilters | None = None, limit: int = DEFAULT_HISTORY_LIMIT, offset: int = 0
) -> Page[StoredRun]:
    """Página de execuções que casam com ``filters``, da mais recente para a mais antiga, com o total.

    Levanta ``ValidationFailed`` se ``limit`` estiver fora de 1 a ``MAX_HISTORY_LIMIT`` ou ``offset`` for negativo.
    """
    # Valida a página antes de abrir qualquer arquivo e depois filtra, corta e conta.
    check_page_args(limit, offset)
    filters = filters or HistoryFilters()
    return paginate((stored for stored in runs.iter_recent() if filters.matches(stored)), limit, offset)


def get_run(runs: RunRepo, run_id: str) -> StoredRun:
    """Execução pelo id. Levanta ``NotFound`` se não existir (o repositório valida o formato do id)."""
    return runs.get(run_id)
