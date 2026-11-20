"""``PromptStore`` sobre a pasta ``prompts/`` (ADR 0005): cada versão é uma subpasta ``vN`` imutável."""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.domain.errors import NotFound, ValidationFailed
from app.domain.prompting.registry import META_FILE, VERSION_PATTERN


class FilePromptStore:
    """Lê versões de prompt do disco. Só aceita nomes ``v<número>``, o que também impede ``../`` na versão."""

    def __init__(self, prompts_dir: Path) -> None:
        self._root = prompts_dir

    def _version_dir(self, version: str) -> Path:
        """Pasta da versão, validando o nome antes de tocar o disco."""
        if not re.fullmatch(VERSION_PATTERN, version):
            raise NotFound(f"Versão de prompt inválida: {version}")
        path = self._root / version
        if not path.is_dir():
            raise NotFound(f"Versão de prompt não encontrada: {version}")
        return path

    def list_versions(self) -> list[str]:
        """Subpastas ``vN`` de ``prompts/`` (outras, como ``judge/``, são ignoradas)."""
        if not self._root.is_dir():
            return []
        return [p.name for p in self._root.iterdir() if p.is_dir() and re.fullmatch(VERSION_PATTERN, p.name)]

    def list_files(self, version: str) -> list[str]:
        """Arquivos da versão, exceto o ``meta.json`` (que guarda o hash dos demais)."""
        folder = self._version_dir(version)
        return sorted(p.name for p in folder.iterdir() if p.is_file() and p.name != META_FILE)

    def read_text(self, version: str, filename: str) -> str:
        """Lê em binário e decodifica, para o hash não variar com a tradução de quebras de linha."""
        folder = self._version_dir(version)
        if filename not in self.list_files(version) and filename != META_FILE:
            raise NotFound(f"Arquivo de prompt não encontrado: {version}/{filename}")
        return (folder / filename).read_bytes().decode("utf-8")

    def read_meta(self, version: str) -> dict:
        """Lê e decodifica o ``meta.json`` da versão."""
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
