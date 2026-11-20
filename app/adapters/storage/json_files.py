"""Repositórios em arquivos JSON (ADR 0009).

Lê o catálogo (``catalog/profiles.json`` e ``catalog/tickets.json``) e oferece o helper de escrita atômica que
será a única forma de gravar dados de execução nas etapas seguintes.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from app.domain.errors import NotFound, ValidationFailed
from app.domain.models import CustomerProfile, Ticket

PROFILES_FILE = "profiles.json"
TICKETS_FILE = "tickets.json"


def atomic_write_json(path: Path, data: Any) -> Path:
    """Grava ``data`` em ``path`` de forma atômica e devolve o caminho.

    Escreve num arquivo temporário na mesma pasta e troca com ``os.replace``. Assim, quem lê nunca vê um
    arquivo pela metade e uma falha no meio não corrompe o arquivo anterior.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp:
            # ensure_ascii=False mantém a acentuação legível no arquivo.
            json.dump(data, tmp, ensure_ascii=False, indent=2)
            tmp.write("\n")
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        # Qualquer falha remove o temporário; o arquivo final anterior permanece intacto.
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return path


def _load_models[ModelT: BaseModel](path: Path, model: type[ModelT]) -> list[ModelT]:
    """Lê uma lista JSON e valida cada item contra ``model``; erros viram ``ValidationFailed``."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValidationFailed(f"Arquivo de catálogo não encontrado: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValidationFailed(f"JSON inválido em {path}: {exc}") from exc
    if not isinstance(raw, list):
        raise ValidationFailed(f"{path.name} deve conter uma lista")
    try:
        items = [model.model_validate(item) for item in raw]
    except ValidationError as exc:
        raise ValidationFailed(f"Item inválido em {path.name}: {exc}") from exc
    ids = [item.id for item in items]  # type: ignore[attr-defined]
    if len(ids) != len(set(ids)):
        raise ValidationFailed(f"Ids duplicados em {path.name}")
    return items


class JsonProfileRepo:
    """``ProfileRepo`` sobre ``<catalog_dir>/profiles.json``. Relê o arquivo a cada consulta (é pequeno)."""

    def __init__(self, catalog_dir: Path) -> None:
        self._path = catalog_dir / PROFILES_FILE

    def list_all(self) -> list[CustomerProfile]:
        return _load_models(self._path, CustomerProfile)

    def get(self, profile_id: str) -> CustomerProfile:
        for profile in self.list_all():
            if profile.id == profile_id:
                return profile
        raise NotFound(f"Perfil não encontrado: {profile_id}")


class JsonTicketRepo:
    """``TicketRepo`` sobre ``<catalog_dir>/tickets.json``."""

    def __init__(self, catalog_dir: Path) -> None:
        self._path = catalog_dir / TICKETS_FILE

    def list_all(self) -> list[Ticket]:
        return _load_models(self._path, Ticket)

    def get(self, ticket_id: str) -> Ticket:
        for ticket in self.list_all():
            if ticket.id == ticket_id:
                return ticket
        raise NotFound(f"Ticket não encontrado: {ticket_id}")
