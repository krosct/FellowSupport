"""Raiz de composição (ADR 0002): único lugar que liga portas a adaptadores concretos.

API e CLI pedem um ``Container`` pronto e nunca instanciam repositórios por conta própria. Etapas seguintes
acrescentam aqui o cliente de LLM (``fake`` ou ``openrouter``), o repositório de execuções e o cache.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.adapters.storage.json_files import JsonProfileRepo, JsonTicketRepo
from app.config import Settings, get_settings
from app.ports.repositories import ProfileRepo, TicketRepo


@dataclass(frozen=True)
class Container:
    """Dependências já ligadas, entregues às camadas de entrada."""

    settings: Settings
    profiles: ProfileRepo
    tickets: TicketRepo


def build_container(settings: Settings | None = None) -> Container:
    """Monta o ``Container`` a partir do ``Settings`` (ou do padrão do processo)."""
    settings = settings or get_settings()
    return Container(
        settings=settings,
        profiles=JsonProfileRepo(settings.catalog_dir),
        tickets=JsonTicketRepo(settings.catalog_dir),
    )
