"""Registro de versões de prompt: lista versões, lê o ``meta.json`` e calcula o hash de conteúdo (ADR 0006).

Uma versão é uma pasta imutável. O ``content_sha256`` do ``meta.json`` é a impressão digital dos arquivos de
prompt; um teste compara com o conteúdo real e falha se alguém editar um prompt sem criar versão nova. O
domínio não toca o disco: lê tudo pela porta ``PromptStore``.
"""

import hashlib
import re
from collections.abc import Iterable, Mapping

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.domain.errors import NotFound, ValidationFailed
from app.ports.repositories import PromptStore

# Metadados, versão base protegida e formato do nome de versão (``v1``, ``v2``...), definidos uma vez.
META_FILE = "meta.json"
BASE_PROMPT_VERSION = "v1"
VERSION_PATTERN = r"v\d+"
PROMPT_FILENAME_PATTERN = r"[A-Za-z0-9][A-Za-z0-9._-]*"
PROMPT_DESCRIPTION_MAX_CHARS = 500
PROMPT_CHANGE_FIELD_MAX_CHARS = 500
PROMPT_FILE_MAX_CHARS = 50000


class PromptChange(BaseModel):
    """Uma mudança em relação à versão-base: o quê, por quê e o efeito esperado (testável na rubrica)."""

    model_config = ConfigDict(frozen=True)

    what: str = Field(min_length=1)
    why: str = Field(min_length=1)
    expected_effect: str = Field(min_length=1)


class PromptVersion(BaseModel):
    """Conteúdo do ``meta.json`` de uma versão de prompt."""

    model_config = ConfigDict(frozen=True)

    version: str = Field(pattern=f"^{VERSION_PATTERN}$")
    based_on: str | None = Field(description="Versão da qual esta deriva; ``None`` na linha de base.")
    description: str = Field(min_length=1)
    created: str = Field(description="Data de criação (AAAA-MM-DD).")
    changes: list[PromptChange]
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$", description="SHA-256 dos arquivos de prompt.")


class PromptDetail(PromptVersion):
    """Versão completa do prompt: metadados do ``meta.json`` e o mapa ``arquivo -> conteúdo``."""

    files: dict[str, str]


def is_valid_prompt_filename(filename: str) -> bool:
    """Confere se o nome do arquivo é seguro (sem barras nem ``meta.json``)."""
    return filename != META_FILE and bool(re.fullmatch(PROMPT_FILENAME_PATTERN, filename))


def compute_content_sha256(files: Mapping[str, str]) -> str:
    """SHA-256 determinístico de um conjunto de arquivos ``nome -> texto``.

    Percorre os nomes em ordem e inclui nome e conteúdo, separados por byte nulo. Assim, renomear, adicionar,
    remover ou alterar um único byte de qualquer arquivo muda o hash.
    """
    # Calcula o hash incluindo nome e conteúdo de cada arquivo em ordem alfabética.
    digest = hashlib.sha256()
    for name in sorted(files):
        digest.update(name.encode("utf-8") + b"\0")
        digest.update(files[name].encode("utf-8") + b"\0")
    return digest.hexdigest()


def _version_key(version: str) -> int:
    """Chave de ordenação numérica (``v2`` antes de ``v10``)."""
    return int(version[1:])


def next_version_name(existing_versions: Iterable[str]) -> str:
    """Próximo identificador ``vN`` disponível (maior número existente + 1)."""
    highest = max((_version_key(v) for v in existing_versions), default=0)
    return f"v{highest + 1}"


class PromptRegistry:
    """Acesso às versões de prompt e à verificação de integridade."""

    def __init__(self, store: PromptStore) -> None:
        self._store = store

    def versions(self) -> list[PromptVersion]:
        """Todas as versões, da mais antiga para a mais nova."""
        names = sorted(self._store.list_versions(), key=_version_key)
        return [self.get(name) for name in names]

    def latest(self) -> PromptVersion:
        """A versão mais nova, sempre a padrão (quem não pede versão recebe esta). ``NotFound`` se não houver."""
        versions = self.versions()
        if not versions:
            raise NotFound("nenhuma versão de prompt encontrada")
        return versions[-1]

    def get(self, version: str) -> PromptVersion:
        """Metadados da versão. ``NotFound`` se não existir; ``ValidationFailed`` se o ``meta.json`` for inválido."""
        # Lê e valida o meta.json confirmando que a versão declarada bate com a pasta.
        raw = self._store.read_meta(version)
        try:
            meta = PromptVersion.model_validate(raw)
        except ValidationError as exc:
            raise ValidationFailed(f"meta.json inválido em {version}: {exc}") from exc
        if meta.version != version:
            raise ValidationFailed(f"meta.json de {version} declara a versão {meta.version}")
        return meta

    def read(self, version: str, filename: str) -> str:
        """Texto de um arquivo de prompt da versão."""
        return self._store.read_text(version, filename)

    def detail(self, version: str) -> PromptDetail:
        """Metadados e todos os arquivos de conteúdo da versão."""
        meta = self.get(version)
        files = {name: self._store.read_text(version, name) for name in sorted(self._store.list_files(version))}
        return PromptDetail(**meta.model_dump(), files=files)

    def has_file(self, version: str, filename: str) -> bool:
        """Indica se a versão tem o arquivo (ex.: se já existe o prompt de um tipo de conteúdo)."""
        try:
            return filename in self._store.list_files(version)
        except NotFound:
            return False

    def snapshot(self, version: str) -> tuple[dict[str, str], str]:
        """Lê todos os arquivos da versão uma única vez e devolve ``(arquivos, sha256)`` consistentes."""
        read_snapshot = getattr(self._store, "read_snapshot", None)
        if callable(read_snapshot):
            files = dict(read_snapshot(version))
        else:
            files = {name: self._store.read_text(version, name) for name in sorted(self._store.list_files(version))}
        return files, compute_content_sha256(files)

    def actual_sha256(self, version: str) -> str:
        """Hash calculado agora sobre os arquivos. É o que vai no registro da execução (``prompt_sha256``)."""
        _, digest = self.snapshot(version)
        return digest

    def verify(self, version: str) -> bool:
        """``True`` se o hash real bate com o ``content_sha256`` do ``meta.json`` (versão não foi editada)."""
        return self.actual_sha256(version) == self.get(version).content_sha256
