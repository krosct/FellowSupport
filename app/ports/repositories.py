"""Portas de repositório (ADR 0002).

O núcleo depende só destes contratos; o armazenamento concreto (JSON em disco hoje, outro amanhã) fica em
``adapters/storage``. Etapas seguintes acrescentam o ``ComparisonRepo``.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol

from app.domain.models import CacheEntry, CustomerProfile, RunRecord, Ticket


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


@dataclass(frozen=True)
class StoredRun:
    """Uma execução lida do armazenamento, com o caminho do arquivo (a API e a CLI mostram onde o JSON está)."""

    record: RunRecord
    saved_path: str


class RunRepo(Protocol):
    """Persistência das execuções: um arquivo por execução (ADR 0009)."""

    def save(self, record: RunRecord) -> str:
        """Grava a execução de forma atômica e devolve o caminho do arquivo (para exibir ao usuário)."""
        ...

    def get(self, run_id: str) -> StoredRun:
        """Execução pelo id. Levanta ``NotFound`` se não existir, se o id for malformado ou o arquivo ilegível."""
        ...

    def iter_recent(self) -> Iterator[StoredRun]:
        """Todas as execuções, da mais recente para a mais antiga, lidas sob demanda.

        Ser preguiçoso deixa o histórico parar de ler arquivos assim que alcança o limite pedido. Arquivos
        ilegíveis são pulados (e registrados em log) em vez de derrubar a listagem inteira.
        """
        ...


class CacheStore(Protocol):
    """Cache de gerações (ADR 0010 e 0028): mapeia a chave canônica para a execução de origem."""

    def get(self, key: str) -> CacheEntry | None:
        """Entrada da chave, ou ``None`` se não existir, se a chave for malformada ou o arquivo estiver corrompido
        (um cache ilegível vale como "não achei", nunca como erro)."""
        ...

    def put(self, entry: CacheEntry) -> None:
        """Grava (ou substitui) a entrada de forma atômica."""
        ...
