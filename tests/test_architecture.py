"""Garante a regra hexagonal (ADR 0002): domínio, portas e serviços não dependem de infraestrutura."""

import ast

from app.config import BASE_DIR

# Bibliotecas e camadas que o núcleo nunca pode importar.
PROIBIDOS = {
    "fastapi", "starlette", "openai", "httpx", "uvicorn", "pydantic_settings",
    "app.adapters", "app.container", "app.config", "pathlib", "os", "tempfile", "shutil",
}


def _imports(pasta: str) -> set[tuple[str, str]]:
    # Extrai todos os módulos importados via AST em cada arquivo .py da pasta.
    achados: set[tuple[str, str]] = set()
    for arquivo in (BASE_DIR / "app" / pasta).rglob("*.py"):
        for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
            if isinstance(no, ast.Import):
                achados.update((arquivo.name, a.name) for a in no.names)
            elif isinstance(no, ast.ImportFrom) and no.module:
                achados.add((arquivo.name, no.module))
    return achados


def test_dominio_portas_e_servicos_nao_importam_infraestrutura() -> None:
    # Garante que nenhuma camada interna importe módulos da lista proibida.
    for pasta in ("domain", "ports", "services"):
        for arquivo, modulo in _imports(pasta):
            for proibido in PROIBIDOS:
                assert not (modulo == proibido or modulo.startswith(proibido + ".")), (
                    f"{pasta}/{arquivo} importa {modulo}"
                )


def test_cli_nao_depende_da_api_nem_de_framework_web() -> None:
    """A CLI é um adaptador de entrada paralelo à API HTTP (ADR 0041), sem importar FastAPI nem adapters/api."""
    proibidos_cli = {"fastapi", "starlette", "uvicorn", "httpx", "app.adapters.api"}
    for arquivo, modulo in _imports("adapters/cli"):
        for proibido in proibidos_cli:
            assert not (modulo == proibido or modulo.startswith(proibido + ".")), (
                f"adapters/cli/{arquivo} importa {modulo}"
            )
