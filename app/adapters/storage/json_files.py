"""Repositórios em arquivos JSON (ADR 0009).

Lê o catálogo (``catalog/profiles.json`` e ``catalog/tickets.json``), grava e lê as execuções (``var/runs/``),
guarda o cache (``var/cache/``) e oferece o helper de escrita atômica, a única forma de gravar dados de execução.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from app.config import BASE_DIR
from app.domain.errors import NotFound, ValidationFailed
from app.domain.models import CACHE_KEY_PATTERN, RUN_ID_PATTERN, CacheEntry, CustomerProfile, RunRecord, Ticket
from app.ports.repositories import StoredRun

logger = logging.getLogger("fellowsupport.storage")

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


# Pastas das execuções e do cache dentro de ``DATA_DIR`` e formato do carimbo no nome do arquivo.
RUNS_DIR = "runs"
CACHE_DIR = "cache"
_FILE_STAMP = "%Y%m%dT%H%M%S"


def display_path(path: Path) -> str:
    """Caminho para mostrar ao usuário: relativo à raiz do repositório quando está dentro dela."""
    try:
        return str(path.relative_to(BASE_DIR))
    except ValueError:
        return str(path)


class JsonRunRepo:
    """``RunRepo`` que grava ``<data_dir>/runs/AAAA-MM-DD/<AAAAMMDDTHHMMSS>_<run_id>.json``."""

    def __init__(self, data_dir: Path) -> None:
        self._runs_dir = data_dir / RUNS_DIR

    def save(self, record: RunRecord) -> str:
        """Grava a execução por escrita atômica. A pasta e o carimbo usam o fuso do próprio ``timestamp``."""
        moment = datetime.fromisoformat(record.timestamp)
        path = self._runs_dir / moment.strftime("%Y-%m-%d") / f"{moment.strftime(_FILE_STAMP)}_{record.run_id}.json"
        atomic_write_json(path, record.model_dump(mode="json"))
        return display_path(path)

    def get(self, run_id: str) -> StoredRun:
        """Procura ``runs/*/*_<run_id>.json``. O id só entra no glob depois de validado (sem curingas nem ``..``)."""
        if not re.fullmatch(RUN_ID_PATTERN, run_id):
            raise NotFound(f"Execução não encontrada: {run_id}")
        for path in self._runs_dir.glob(f"*/*_{run_id}.json"):
            return self._read(path)
        raise NotFound(f"Execução não encontrada: {run_id}")

    def iter_recent(self) -> Iterator[StoredRun]:
        """Percorre os arquivos do mais novo para o mais antigo, lendo um por vez.

        O carimbo no início do nome (``AAAAMMDDTHHMMSS``) ordena por data; o ``mtime`` desempata execuções do
        mesmo segundo (ex.: as quatro do modo ``all``), para a mais recente vir primeiro de fato.
        """
        paths = sorted(
            self._runs_dir.glob("*/*.json"),
            key=lambda path: (path.name.split("_", 1)[0], path.stat().st_mtime_ns),
            reverse=True,
        )
        for path in paths:
            try:
                yield self._read(path)
            except NotFound:
                continue  # arquivo ilegível: já registrado em log; o histórico segue com os demais

    @staticmethod
    def _read(path: Path) -> StoredRun:
        """Lê e valida um arquivo de execução. Falha de leitura ou de formato vira ``NotFound`` com log."""
        try:
            record = RunRecord.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:  # ValidationError e JSON inválido herdam de ValueError
            logger.warning("execução ilegível em %s: %s", display_path(path), type(exc).__name__)
            raise NotFound(f"Execução ilegível: {display_path(path)}") from exc
        return StoredRun(record=record, saved_path=display_path(path))


class JsonCacheStore:
    """``CacheStore`` que grava ``<data_dir>/cache/<sha256>.json`` (ADR 0009 e 0010).

    Cada arquivo guarda só o ponteiro para a execução de origem; a saída em si continua em ``var/runs/``.
    """

    def __init__(self, data_dir: Path) -> None:
        self._cache_dir = data_dir / CACHE_DIR

    def get(self, key: str) -> CacheEntry | None:
        """Lê a entrada da chave. Chave malformada, arquivo ausente ou corrompido devolvem ``None``."""
        if not re.fullmatch(CACHE_KEY_PATTERN, key):
            return None
        path = self._cache_dir / f"{key}.json"
        try:
            entry = CacheEntry.model_validate_json(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as exc:
            logger.warning("entrada de cache ilegível em %s: %s", display_path(path), type(exc).__name__)
            return None
        # Um arquivo copiado ou renomeado à mão não pode responder por outra chave.
        return entry if entry.cache_key == key else None

    def put(self, entry: CacheEntry) -> None:
        """Grava a entrada por escrita atômica; duas gerações simultâneas da mesma chave não corrompem o arquivo."""
        if not re.fullmatch(CACHE_KEY_PATTERN, entry.cache_key):
            raise ValidationFailed(f"Chave de cache inválida: {entry.cache_key}")
        atomic_write_json(self._cache_dir / f"{entry.cache_key}.json", entry.model_dump(mode="json"))
