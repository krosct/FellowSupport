"""``PromptStore`` sobre a pasta ``prompts/`` (ADR 0005): cada versão é uma subpasta ``vN``."""

import json
import re
import shutil
import threading
from collections.abc import Mapping
from pathlib import Path

from app.adapters.storage.json_files import atomic_write_json
from app.domain.errors import NotFound, ValidationFailed
from app.domain.prompting.registry import META_FILE, VERSION_PATTERN, is_valid_prompt_filename


class FilePromptStore:
    """Lê e grava versões de prompt no disco. Só aceita nomes ``v<número>``, o que também impede ``../``."""

    def __init__(self, prompts_dir: Path) -> None:
        self._root = prompts_dir
        self._lock = threading.Lock()

    def _version_dir(self, version: str) -> Path:
        """Pasta da versão, validando o nome antes de tocar o disco."""
        # Garante nome de versão vN seguro antes de montar o caminho da pasta.
        if not re.fullmatch(VERSION_PATTERN, version):
            raise NotFound(f"Versão de prompt inválida: {version}")
        path = self._root / version
        if not path.is_dir():
            raise NotFound(f"Versão de prompt não encontrada: {version}")
        return path

    def list_versions(self) -> list[str]:
        """Subpastas ``vN`` de ``prompts/`` (demais subpastas são ignoradas)."""
        with self._lock:
            if not self._root.is_dir():
                return []
            return [p.name for p in self._root.iterdir() if p.is_dir() and re.fullmatch(VERSION_PATTERN, p.name)]

    def list_files(self, version: str) -> list[str]:
        """Arquivos da versão, exceto o ``meta.json`` (que guarda o hash dos demais)."""
        # Lista todos os arquivos da pasta da versão ignorando o meta.json.
        with self._lock:
            folder = self._version_dir(version)
            return sorted(p.name for p in folder.iterdir() if p.is_file() and p.name != META_FILE)

    def read_text(self, version: str, filename: str) -> str:
        """Lê em binário e decodifica, para o hash não variar com a tradução de quebras de linha."""
        # Lê em modo binário para não alterar quebras de linha e manter o hash fiel.
        with self._lock:
            folder = self._version_dir(version)
            allowed = {p.name for p in folder.iterdir() if p.is_file() and p.name != META_FILE}
            if filename not in allowed and filename != META_FILE:
                raise NotFound(f"Arquivo de prompt não encontrado: {version}/{filename}")
            return (folder / filename).read_bytes().decode("utf-8")

    def read_snapshot(self, version: str) -> dict[str, str]:
        """Lê todos os arquivos de conteúdo da versão em uma única aquisição de lock."""
        with self._lock:
            folder = self._version_dir(version)
            names = sorted(p.name for p in folder.iterdir() if p.is_file() and p.name != META_FILE)
            return {name: (folder / name).read_bytes().decode("utf-8") for name in names}

    def read_meta(self, version: str) -> dict:
        """Lê e decodifica o ``meta.json`` da versão."""
        # Lê e valida o objeto JSON do meta.json da versão.
        with self._lock:
            folder = self._version_dir(version)
            try:
                data = json.loads((folder / META_FILE).read_text(encoding="utf-8"))
            except FileNotFoundError as exc:
                raise ValidationFailed(f"{version}/{META_FILE} não encontrado") from exc
            except json.JSONDecodeError as exc:
                raise ValidationFailed(f"JSON inválido em {version}/{META_FILE}: {exc}") from exc
            if not isinstance(data, dict):
                raise ValidationFailed(f"{version}/{META_FILE} deve ser um objeto JSON")
            return data

    def _validate_filenames(self, files: Mapping[str, str]) -> None:
        """Garante nomes seguros antes de escrever qualquer arquivo na pasta da versão."""
        for filename in files:
            if not is_valid_prompt_filename(filename):
                raise ValidationFailed(f"Nome de arquivo de prompt inválido: {filename!r}")

    def create_version(self, version: str, meta: dict, files: Mapping[str, str]) -> None:
        """Cria a pasta ``prompts/<version>/`` com os arquivos e o ``meta.json``."""
        if not re.fullmatch(VERSION_PATTERN, version):
            raise ValidationFailed(f"Versão de prompt inválida: {version}")
        self._validate_filenames(files)
        with self._lock:
            folder = self._root / version
            if folder.exists():
                raise ValidationFailed(f"Versão de prompt já existe: {version}")
            folder.mkdir(parents=True, exist_ok=False)
            try:
                for filename, content in files.items():
                    (folder / filename).write_bytes(content.encode("utf-8"))
                atomic_write_json(folder / META_FILE, meta)
            except BaseException:
                shutil.rmtree(folder, ignore_errors=True)
                raise

    def delete_version(self, version: str) -> None:
        """Remove a pasta ``prompts/<version>/`` e todos os seus arquivos."""
        with self._lock:
            folder = self._version_dir(version)
            shutil.rmtree(folder)
