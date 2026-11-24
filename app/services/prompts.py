"""CRUD de versões de prompt (leitura detalhada, criação a partir de versão-base e remoção).

Toda criação recalcula o ``content_sha256`` determinístico e grava os arquivos e a pasta da versão via
``EditablePromptStore``. Versões são imutáveis (ADR 0006): não há edição in-place. A versão base ``v1`` não pode ser
removida e toda versão criada exige uma versão-base (``based_on``) existente.
"""

import threading
from collections.abc import Mapping, Sequence
from zoneinfo import ZoneInfo

from app.domain.errors import ValidationFailed
from app.domain.prompting.engine import validate_prompt_files
from app.domain.prompting.registry import (
    BASE_PROMPT_VERSION,
    PROMPT_CHANGE_FIELD_MAX_CHARS,
    PROMPT_DESCRIPTION_MAX_CHARS,
    PromptChange,
    PromptDetail,
    PromptRegistry,
    PromptVersion,
    compute_content_sha256,
    next_version_name,
)
from app.ports.repositories import EditablePromptStore
from app.services.clock import Clock, system_clock
from app.services.meta import PromptVersionInfo, list_prompt_versions

_CREATE_LOCK = threading.Lock()


class PromptVersionDetail(PromptVersionInfo):
    """Versão de prompt completa: metadados (com ``is_default``) e mapa ``arquivo -> conteúdo``."""

    files: dict[str, str]


def _required_text(value: str, label: str, max_chars: int) -> str:
    """Apara espaços e garante texto não vazio dentro do limite."""
    cleaned = value.strip()
    if not cleaned:
        raise ValidationFailed(f"Informe {label}.")
    if len(cleaned) > max_chars:
        raise ValidationFailed(f"{label[0].upper()}{label[1:]} passa do limite de {max_chars} caracteres.")
    return cleaned


def _normalize_changes(changes: Sequence[PromptChange]) -> list[PromptChange]:
    """Valida e apara os três campos de cada mudança registrada."""
    return [
        PromptChange(
            what=_required_text(item.what, "o que mudou", PROMPT_CHANGE_FIELD_MAX_CHARS),
            why=_required_text(item.why, "o porquê da mudança", PROMPT_CHANGE_FIELD_MAX_CHARS),
            expected_effect=_required_text(
                item.expected_effect, "o efeito esperado", PROMPT_CHANGE_FIELD_MAX_CHARS
            ),
        )
        for item in changes
    ]


def _to_detail(registry: PromptRegistry, detail: PromptDetail) -> PromptVersionDetail:
    """Acrescenta ``is_default`` ao detalhe da versão usando a regra única do registro."""
    latest_version = registry.latest().version
    return PromptVersionDetail(**detail.model_dump(), is_default=detail.version == latest_version)


def get_prompt(registry: PromptRegistry, version: str) -> PromptVersionDetail:
    """Metadados e arquivos de uma versão de prompt. Levanta ``NotFound`` se não existir."""
    return _to_detail(registry, registry.detail(version))


def create_prompt(
    store: EditablePromptStore,
    registry: PromptRegistry,
    *,
    based_on: str,
    description: str,
    changes: Sequence[PromptChange],
    files: Mapping[str, str],
    timezone: str,
    clock: Clock = system_clock,
) -> PromptVersionDetail:
    """Cria uma nova versão de prompt derivada de ``based_on``, calculando o hash e gravando os arquivos."""
    source = based_on.strip()
    if not source:
        raise ValidationFailed("Informe a versão base (source) para criar um prompt.")
    registry.get(source)

    clean_description = _required_text(description, "a descrição do prompt", PROMPT_DESCRIPTION_MAX_CHARS)
    clean_changes = _normalize_changes(changes)
    normalized_files = validate_prompt_files(files)
    content_hash = compute_content_sha256(normalized_files)
    created_date = clock(ZoneInfo(timezone)).date().isoformat()

    with _CREATE_LOCK:
        version = next_version_name(store.list_versions())
        meta = PromptVersion(
            version=version,
            based_on=source,
            description=clean_description,
            created=created_date,
            changes=clean_changes,
            content_sha256=content_hash,
        )
        store.create_version(version, meta.model_dump(mode="json"), normalized_files)

    return get_prompt(registry, version)


def delete_prompt(store: EditablePromptStore, registry: PromptRegistry, version: str) -> PromptVersionInfo:
    """Remove a pasta e os arquivos de uma versão derivada. A versão base ``v1`` não pode ser removida."""
    if version == BASE_PROMPT_VERSION:
        raise ValidationFailed(f"A versão base {BASE_PROMPT_VERSION} não pode ser removida.")
    versions = list_prompt_versions(registry)
    target = next((item for item in versions if item.version == version), None)
    if target is None:
        registry.get(version)  # levanta NotFound padronizado
        raise AssertionError("inacessível")
    store.delete_version(version)
    return target
