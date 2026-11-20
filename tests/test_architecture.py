"""Garante a regra hexagonal (ADR 0002): domínio e portas não dependem de infraestrutura."""

from __future__ import annotations

import ast

from app.config import BASE_DIR

# Bibliotecas e camadas que o núcleo nunca pode importar.
PROIBIDOS = {
    "fastapi", "starlette", "openai", "httpx", "uvicorn", "pydantic_settings",
    "app.adapters", "app.container",
}


def _imports(pasta: str) -> set[tuple[str, str]]:
    achados: set[tuple[str, str]] = set()
    for arquivo in (BASE_DIR / "app" / pasta).rglob("*.py"):
        for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
            if isinstance(no, ast.Import):
                achados.update((arquivo.name, a.name) for a in no.names)
            elif isinstance(no, ast.ImportFrom) and no.module:
                achados.add((arquivo.name, no.module))
    return achados


def test_dominio_e_portas_nao_importam_infraestrutura() -> None:
    for pasta in ("domain", "ports"):
        for arquivo, modulo in _imports(pasta):
            for proibido in PROIBIDOS:
                assert not (modulo == proibido or modulo.startswith(proibido + ".")), (
                    f"{pasta}/{arquivo} importa {modulo}"
                )
