"""Repositórios em arquivos JSON (ADR 0009).

Lê e edita o catálogo (``catalog/profiles.json`` e ``catalog/tickets.json``), grava e lê as execuções
(``var/runs/``), guarda o cache (``var/cache/``) e oferece o helper de escrita atômica, a única forma de gravar
dados de execução.
"""

import json
import logging
import os
import re
import tempfile
import threading
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.config import BASE_DIR
from app.domain.comparison import COMPARISON_ID_PATTERN, ComparisonRecord
from app.domain.errors import NotFound, ValidationFailed
from app.domain.models import (
    CACHE_KEY_PATTERN,
    MAX_CATALOG_PROFILES,
    MAX_CATALOG_TICKETS,
    RUN_ID_PATTERN,
    CacheEntry,
    CustomerProfile,
    RunRecord,
    Ticket,
)
from app.ports.repositories import StoredComparison, StoredRun

logger = logging.getLogger("fellowsupport.storage")

PROFILES_FILE = "profiles.json"
TICKETS_FILE = "tickets.json"


def atomic_write_json(path: Path, data: Any) -> Path:
    """Grava ``data`` em ``path`` de forma atômica e devolve o caminho.

    Escreve num arquivo temporário na mesma pasta e troca com ``os.replace``. Assim, quem lê nunca vê um
    arquivo pela metade e uma falha no meio não corrompe o arquivo anterior.
    """
    # Escreve em arquivo temporário na mesma pasta, força flush e troca atomicamente.
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


def _load_models[ModelT: (CustomerProfile, Ticket)](path: Path, model: type[ModelT]) -> list[ModelT]:
    """Lê uma lista JSON e valida cada item contra ``model``; erros viram ``ValidationFailed``."""
    # Lê lista JSON, valida cada item com Pydantic e impede ids repetidos.
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
    ids = [item.id for item in items]
    if len(ids) != len(set(ids)):
        raise ValidationFailed(f"Ids duplicados em {path.name}")
    return items


class _JsonCatalog[ModelT: (CustomerProfile, Ticket)]:
    """Catálogo em ``<catalog_dir>/<arquivo>.json``: lê, cria, edita e remove itens (ADR 0037).

    O arquivo é a única fonte: cada operação relê a lista, altera e grava de forma atômica (o arquivo é pequeno).
    Um ``Lock`` serializa ler-alterar-gravar, porque o serviço roda em threads (ADR 0015) e, sem ele, duas escritas
    perderiam uma delas. As subclasses só dizem o modelo, o arquivo, o nome do item e o limite de itens.
    """

    _model: type[ModelT]
    _file: str
    _noun: str  # nome do item nas mensagens de erro, com a inicial maiúscula (ex.: "Ticket")
    _max_items: int

    def __init__(self, catalog_dir: Path) -> None:
        self._path = catalog_dir / self._file
        self._lock = threading.Lock()

    def _read(self) -> list[ModelT]:
        return _load_models(self._path, self._model)

    def _write(self, items: list[ModelT]) -> None:
        atomic_write_json(self._path, [item.model_dump(mode="json") for item in items])

    def list_all(self) -> list[ModelT]:
        """Todos os itens, na ordem do arquivo (a ordem de criação para os novos)."""
        with self._lock:
            return self._read()

    def get(self, item_id: str) -> ModelT:
        """Item pelo id; ``NotFound`` se não existir."""
        for item in self.list_all():
            if item.id == item_id:
                return item
        raise NotFound(f"{self._noun} não encontrado: {item_id}")

    def add(self, item: ModelT) -> ModelT:
        """Acrescenta o item ao fim; recusa id repetido e lista cheia."""
        with self._lock:
            items = self._read()
            if any(existing.id == item.id for existing in items):
                raise ValidationFailed(f"Já existe um item com o id {item.id}")
            if len(items) >= self._max_items:
                raise ValidationFailed(f"O catálogo já tem {self._max_items} itens, o máximo. Remova algum antes.")
            self._write([*items, item])
        return item

    def update(self, item: ModelT) -> ModelT:
        """Troca o item de mesmo id, mantendo a posição na lista."""
        with self._lock:
            items = self._read()
            if not any(existing.id == item.id for existing in items):
                raise NotFound(f"{self._noun} não encontrado: {item.id}")
            self._write([item if existing.id == item.id else existing for existing in items])
        return item

    def remove(self, item_id: str) -> ModelT:
        """Remove o item e o devolve."""
        with self._lock:
            items = self._read()
            removed = next((item for item in items if item.id == item_id), None)
            if removed is None:
                raise NotFound(f"{self._noun} não encontrado: {item_id}")
            self._write([item for item in items if item.id != item_id])
        return removed


class JsonProfileRepo(_JsonCatalog[CustomerProfile]):
    """``ProfileStore`` sobre ``<catalog_dir>/profiles.json``."""

    _model = CustomerProfile
    _file = PROFILES_FILE
    _noun = "Perfil"
    _max_items = MAX_CATALOG_PROFILES


class JsonTicketRepo(_JsonCatalog[Ticket]):
    """``TicketStore`` sobre ``<catalog_dir>/tickets.json``."""

    _model = Ticket
    _file = TICKETS_FILE
    _noun = "Ticket"
    _max_items = MAX_CATALOG_TICKETS


# Pastas das execuções e do cache dentro de ``DATA_DIR`` e formato do carimbo no nome do arquivo.
RUNS_DIR = "runs"
CACHE_DIR = "cache"
COMPARISONS_DIR = "comparisons"
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
        # Organiza o arquivo em subpasta por data (YYYY-MM-DD) e grava atomicamente.
        moment = datetime.fromisoformat(record.timestamp)
        path = self._runs_dir / moment.strftime("%Y-%m-%d") / f"{moment.strftime(_FILE_STAMP)}_{record.run_id}.json"
        atomic_write_json(path, record.model_dump(mode="json"))
        return display_path(path)

    def get(self, run_id: str) -> StoredRun:
        """Procura ``runs/*/*_<run_id>.json``. O id só entra no glob depois de validado (sem curingas nem ``..``)."""
        # Valida o padrão hexadecimal do id antes de buscar no disco.
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
        # Ordena por carimbo e mtime decrescente, pulando arquivos corrompidos.
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
        # Valida formato da chave, lê a entrada e ignora arquivo ausente ou inválido.
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


class JsonComparisonRepo:
    """``ComparisonRepo`` que grava ``<data_dir>/comparisons/<id>.json`` (ADR 0031).

    Um arquivo por comparação, com o id no nome (e não um carimbo): o caminho é previsível a partir do id. A ordem da
    listagem vem do ``created_at`` gravado no registro, não do nome nem do ``mtime``.
    """

    def __init__(self, data_dir: Path) -> None:
        self._dir = data_dir / COMPARISONS_DIR

    def save(self, record: ComparisonRecord) -> str:
        """Grava a comparação por escrita atômica e devolve o caminho exibível."""
        path = self._dir / f"{record.comparison_id}.json"
        atomic_write_json(path, record.model_dump(mode="json"))
        return display_path(path)

    def get(self, comparison_id: str) -> StoredComparison:
        """Lê a comparação. O id só toca o disco depois de validado (sem curingas nem ``..``)."""
        if not re.fullmatch(COMPARISON_ID_PATTERN, comparison_id):
            raise NotFound(f"Comparação não encontrada: {comparison_id}")
        path = self._dir / f"{comparison_id}.json"
        if not path.is_file():
            raise NotFound(f"Comparação não encontrada: {comparison_id}")
        return self._read(path)

    def list_recent(self) -> list[StoredComparison]:
        """Todas as comparações legíveis, da mais recente para a mais antiga (``created_at``, depois id)."""
        # Lê todas as comparações válidas e ordena da mais recente à mais antiga.
        found = []
        for path in self._dir.glob("*.json"):
            try:
                found.append(self._read(path))
            except NotFound:
                continue  # arquivo ilegível: já registrado em log; a listagem segue com os demais
        return sorted(found, key=lambda item: (item.record.created_at, item.record.comparison_id), reverse=True)

    @staticmethod
    def _read(path: Path) -> StoredComparison:
        """Lê e valida um arquivo de comparação. Falha de leitura ou de formato vira ``NotFound`` com log."""
        try:
            record = ComparisonRecord.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:  # ValidationError e JSON inválido herdam de ValueError
            logger.warning("comparação ilegível em %s: %s", display_path(path), type(exc).__name__)
            raise NotFound(f"Comparação ilegível: {display_path(path)}") from exc
        return StoredComparison(record=record, saved_path=display_path(path))
