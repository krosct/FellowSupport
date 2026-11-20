"""Portas de repositório (ADR 0002).

O núcleo depende só destes contratos; o armazenamento concreto (JSON em disco hoje, outro amanhã) fica em
``adapters/storage``. Etapas seguintes acrescentam ``ComparisonRepo`` e ``CacheStore``.
"""

from __future__ import annotations

from typing import Protocol

from app.domain.models import CustomerProfile, RunRecord, Ticket


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


class PromptStore(Protocol):
    """Leitura dos arquivos de prompt versionados (``prompts/<versão>/``).

    O registro de versões (domínio) calcula hash e valida metadados; esta porta só entrega nomes e textos, para
    o domínio não tocar o disco.
    """

    def list_versions(self) -> list[str]:
        """Nomes das versões existentes (ex.: ``["v1", "v2"]``), sem ordem garantida."""
        ...

    def list_files(self, version: str) -> list[str]:
        """Nomes dos arquivos de conteúdo da versão, sem o ``meta.json``. Levanta ``NotFound`` se não existir."""
        ...

    def read_text(self, version: str, filename: str) -> str:
        """Texto exato do arquivo (sem tradução de quebras de linha). Levanta ``NotFound`` se não existir."""
        ...

    def read_meta(self, version: str) -> dict:
        """Conteúdo do ``meta.json`` da versão. Levanta ``NotFound`` ou ``ValidationFailed`` (JSON inválido)."""
        ...


class RunRepo(Protocol):
    """Persistência das execuções: um arquivo por execução (ADR 0009)."""

    def save(self, record: RunRecord) -> str:
        """Grava a execução de forma atômica e devolve o caminho do arquivo (para exibir ao usuário)."""
        ...
