"""Portas de repositório (ADR 0002).

O núcleo depende só destes contratos; o armazenamento concreto (JSON em disco hoje, outro amanhã) fica em
``adapters/storage``. ``ComparisonRepo`` guarda as comparações salvas.
"""

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Protocol

from app.domain.comparison import ComparisonRecord
from app.domain.models import CacheEntry, CustomerProfile, RunRecord, Ticket


# Portas do catálogo (perfis e tickets): leitura nos ``*Repo`` e escrita nos ``*Store``.
class ProfileRepo(Protocol):
    """Acesso aos perfis de cliente (leitura; usada pelos geradores)."""

    def list_all(self) -> list[CustomerProfile]:
        """Todos os perfis, na ordem do catálogo."""
        ...

    def get(self, profile_id: str) -> CustomerProfile:
        """Perfil pelo id. Levanta ``NotFound`` se não existir."""
        ...


class ProfileStore(ProfileRepo, Protocol):
    """Catálogo de perfis editável: além de ler, cria, edita e remove (ADR 0037)."""

    def add(self, profile: CustomerProfile) -> CustomerProfile:
        """Grava um perfil novo no fim. Levanta ``ValidationFailed`` se o id já existir ou o limite estourar."""
        ...

    def update(self, profile: CustomerProfile) -> CustomerProfile:
        """Troca o perfil de mesmo id. Levanta ``NotFound`` se não existir."""
        ...

    def remove(self, profile_id: str) -> CustomerProfile:
        """Remove e devolve o perfil. Levanta ``NotFound`` se não existir."""
        ...


class TicketRepo(Protocol):
    """Acesso aos tickets (leitura; usada pelos geradores)."""

    def list_all(self) -> list[Ticket]:
        """Todos os tickets, na ordem do catálogo."""
        ...

    def get(self, ticket_id: str) -> Ticket:
        """Ticket pelo id. Levanta ``NotFound`` se não existir."""
        ...


class TicketStore(TicketRepo, Protocol):
    """Catálogo de tickets editável: além de ler, cria, edita e remove (ADR 0037)."""

    def add(self, ticket: Ticket) -> Ticket:
        """Grava um ticket novo no fim. Levanta ``ValidationFailed`` se o id já existir ou o limite estourar."""
        ...

    def update(self, ticket: Ticket) -> Ticket:
        """Troca título e texto do ticket de mesmo id. Levanta ``NotFound`` se não existir."""
        ...

    def remove(self, ticket_id: str) -> Ticket:
        """Remove e devolve o ticket. Levanta ``NotFound`` se não existir."""
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


class EditablePromptStore(PromptStore, Protocol):
    """Armazenamento de versões de prompt: cria e remove pastas ``prompts/<versão>/`` (imutáveis)."""

    def create_version(self, version: str, meta: dict, files: Mapping[str, str]) -> None:
        """Cria a pasta da versão com os arquivos e o ``meta.json``. ``ValidationFailed`` se já existir."""
        ...

    def delete_version(self, version: str) -> None:
        """Remove a pasta da versão e todos os seus arquivos. ``NotFound`` se não existir."""
        ...


# Portas de persistência de execuções, caches e comparações.
@dataclass(frozen=True)
class StoredRun:
    """Uma execução lida do armazenamento, com o caminho do arquivo (a API e a CLI mostram onde o JSON está)."""

    record: RunRecord
    saved_path: str


class RunRepo(Protocol):
    """Persistência das execuções: um arquivo por execução (ADR 0009)."""

    def save(self, record: RunRecord) -> str:
        """Grava a execução de forma atômica e devolve o caminho do arquivo (para exibir ao usuário).

        Regravar um registro com o mesmo ``run_id`` e ``timestamp`` substitui o arquivo (é assim que a avaliação
        entra na execução), sempre por troca atômica.
        """
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


@dataclass(frozen=True)
class StoredComparison:
    """Uma comparação lida do armazenamento, com o caminho do arquivo."""

    record: ComparisonRecord
    saved_path: str


class ComparisonRepo(Protocol):
    """Persistência das comparações: um arquivo por comparação em ``var/comparisons/<id>.json`` (ADR 0031)."""

    def save(self, record: ComparisonRecord) -> str:
        """Grava a comparação de forma atômica e devolve o caminho do arquivo (para exibir ao usuário)."""
        ...

    def get(self, comparison_id: str) -> StoredComparison:
        """Comparação pelo id. Levanta ``NotFound`` se não existir, se o id for malformado ou o arquivo ilegível."""
        ...

    def list_recent(self) -> list[StoredComparison]:
        """Todas as comparações, da mais recente para a mais antiga. Arquivos ilegíveis são pulados (com log)."""
        ...
