"""Portas de repositório (ADR 0002).

O núcleo depende só destes contratos; o armazenamento concreto (JSON em disco hoje, outro amanhã) fica em
``adapters/storage``. Etapas seguintes acrescentam ``RunRepo``, ``ComparisonRepo`` e ``CacheStore``.
"""

from __future__ import annotations

from typing import Protocol

from app.domain.models import CustomerProfile, Ticket


class ProfileRepo(Protocol):
    """Acesso aos perfis de cliente."""

    def list_all(self) -> list[CustomerProfile]:
        """Todos os perfis, na ordem do catálogo."""
        ...

    def get(self, profile_id: str) -> CustomerProfile:
        """Perfil pelo id. Levanta ``NotFound`` se não existir."""
        ...


class TicketRepo(Protocol):
    """Acesso aos tickets de exemplo."""

    def list_all(self) -> list[Ticket]:
        """Todos os tickets, na ordem do catálogo."""
        ...

    def get(self, ticket_id: str) -> Ticket:
        """Ticket pelo id. Levanta ``NotFound`` se não existir."""
        ...
