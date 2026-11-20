"""Aplicação FastAPI: monta as rotas, traduz erros do domínio e serve o build do front (ADR 0012).

Execução: ``uvicorn app.adapters.api.main:app --port 8000``.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.adapters.api.routers import api_router, health_router
from app.config import FRONTEND_DIST
from app.container import Container, build_container
from app.domain.errors import (
    DomainError,
    InvalidLLMOutput,
    LLMRateLimited,
    LLMUnavailable,
    NotFound,
    ValidationFailed,
)

logger = logging.getLogger("fellowsupport.api")

# Tradução única erro do domínio -> status HTTP (ADR 0018).
ERROR_STATUS: dict[type[DomainError], int] = {
    NotFound: 404,
    ValidationFailed: 422,
    LLMRateLimited: 429,
    InvalidLLMOutput: 502,
    LLMUnavailable: 503,
}


async def _domain_error_handler(_: Request, exc: Exception) -> JSONResponse:
    """Converte ``DomainError`` em JSON ``{"detail": ...}`` com o status mapeado."""
    status = next((code for cls, code in ERROR_STATUS.items() if isinstance(exc, cls)), 500)
    return JSONResponse(status_code=status, content={"detail": str(exc)})


def create_app(container: Container | None = None, frontend_dist: Path | None = FRONTEND_DIST) -> FastAPI:
    """Fábrica da aplicação.

    ``container`` e ``frontend_dist`` são parametrizáveis para que os testes usem catálogo e pastas temporárias.
    """
    container = container or build_container()
    logging.basicConfig(level=container.settings.log_level)

    app = FastAPI(title="FellowSupport", version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.state.container = container
    app.add_exception_handler(DomainError, _domain_error_handler)
    app.include_router(health_router)
    app.include_router(api_router)

    # O build do React é montado por último: as rotas acima têm prioridade e só o que sobra cai nos estáticos.
    # Sem a pasta (ex.: desenvolvimento ou testes), a API funciona normalmente.
    if frontend_dist is not None and frontend_dist.is_dir():
        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
    else:
        logger.info("frontend/dist não encontrado: servindo apenas a API")
    return app


# Instância usada pelo uvicorn.
app = create_app()
