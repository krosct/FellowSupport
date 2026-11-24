"""Adaptador do log de eventos (ADR 0043): um arquivo JSON Lines, um evento por linha.

Cada linha é um objeto JSON com ``ts`` (ISO 8601 no fuso de ``APP_TIMEZONE``), ``event``, ``pid`` e os campos do
evento. JSON Lines porque cada linha se lê sozinha (``tail -f``, ``grep``, ``jq``) e o arquivo cresce só por
acréscimo, sem reescrever nada.

A escrita usa ``O_APPEND`` e um único ``os.write`` por linha: com a API e a CLI escrevendo ao mesmo tempo, as linhas
não se misturam. Um lock evita a mistura entre as threads do modo ``all``. Falhar ao registrar só gera um aviso: o
log nunca derruba a geração.
"""

import json
import logging
import os
import threading
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

logger = logging.getLogger("fellowsupport.events")

# Permissão do arquivo de log: só o dono lê e escreve, como os JSONs de execução (o log traz ids de clientes).
LOG_FILE_MODE = 0o600


class JsonLinesEventLog:
    """``EventLog`` que acrescenta cada evento como uma linha JSON em ``path``."""

    def __init__(self, path: Path, timezone: str) -> None:
        """Guarda o destino e o fuso; o arquivo só é criado no primeiro evento."""
        self._path = path
        self._zone = ZoneInfo(timezone)
        self._lock = threading.Lock()

    @property
    def path(self) -> Path:
        """Caminho do arquivo de log."""
        return self._path

    def emit(self, event: str, fields: Mapping[str, object]) -> None:
        """Acrescenta o evento ao arquivo; em caso de erro de disco, só registra um aviso."""
        entry = {
            "ts": datetime.now(self._zone).isoformat(timespec="milliseconds"),
            "event": event,
            "pid": os.getpid(),
            **fields,
        }
        # default=str cobre valores fora do JSON (enums, caminhos) sem perder o evento.
        line = (json.dumps(entry, ensure_ascii=False, default=str) + "\n").encode("utf-8")
        try:
            with self._lock:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                fd = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, LOG_FILE_MODE)
                try:
                    os.write(fd, line)
                finally:
                    os.close(fd)
        except OSError as exc:
            logger.warning("não foi possível gravar o evento %s em %s: %s", event, self._path, exc)
