"""Aplicação FastAPI: monta as rotas, traduz erros do domínio e serve o build do front (ADR 0012).

Execução: ``uvicorn app.adapters.api.main:app --port 9713``.
"""

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.adapters.api.ratelimit import SlidingWindowLimiter
from app.adapters.api.routers import api_router, health_router
from app.config import FRONTEND_DIST
from app.container import Container, build_container
from app.domain.errors import (
    CacheReplaceRequired,
    DomainError,
    Forbidden,
    InvalidLLMOutput,
    LLMRateLimited,
    LLMUnavailable,
    NotFound,
    Unauthorized,
    ValidationFailed,
)

logger = logging.getLogger("fellowsupport.api")

# Valor do campo ``code`` do 409 de substituição de cache; o front compara com ele (ADR 0036).
CACHE_REPLACE_CODE = "cache_replace_required"

# Tradução única erro do domínio -> status HTTP (ADR 0018).
ERROR_STATUS: dict[type[DomainError], int] = {
    Unauthorized: 401,
    Forbidden: 403,
    NotFound: 404,
    CacheReplaceRequired: 409,
    ValidationFailed: 422,
    LLMRateLimited: 429,
    InvalidLLMOutput: 502,
    LLMUnavailable: 503,
}


async def _domain_error_handler(_: Request, exc: Exception) -> JSONResponse:
    """Converte ``DomainError`` em JSON ``{"detail": ...}`` com o status mapeado.

    O 409 de substituição de cache leva também ``code`` e ``conflicts`` (todas as entradas afetadas), para o cliente
    mostrá-las numa confirmação só e repetir o pedido com ``confirm_replace`` (ADR 0036).
    """
    # Busca o status HTTP mapeado para a exceção ou cai em 500 (Internal Server Error) por segurança.
    status = next((code for cls, code in ERROR_STATUS.items() if isinstance(exc, cls)), 500)
    content: dict = {"detail": str(exc)}
    if isinstance(exc, CacheReplaceRequired):
        content["code"] = CACHE_REPLACE_CODE
        content["conflicts"] = [conflict.model_dump(mode="json") for conflict in exc.conflicts]
    return JSONResponse(status_code=status, content=content)


def create_app(
    container: Container | None = None,
    frontend_dist: Path | None = FRONTEND_DIST,
    rate_limiter: SlidingWindowLimiter | None = None,
) -> FastAPI:
    """Fábrica da aplicação.

    ``container``, ``frontend_dist`` e ``rate_limiter`` são parametrizáveis para que os testes usem catálogo e pastas
    temporárias e um relógio controlado. Sem ``rate_limiter``, o limite por IP vem de ``RATE_LIMIT_PER_MIN``.
    """
    # Inicializa container, logger, app FastAPI, limitador por IP e rotas.
    container = container or build_container()
    logging.basicConfig(level=container.settings.log_level)

    app = FastAPI(title="FellowSupport", version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.state.container = container
    app.state.rate_limiter = rate_limiter or SlidingWindowLimiter(container.settings.rate_limit_per_min)
    app.add_exception_handler(DomainError, _domain_error_handler)
    app.include_router(health_router)
    app.include_router(api_router)

    # O build do React é montado por último: as rotas acima têm prioridade e só o que sobra cai nos estáticos.
    # Sem a pasta (ex.: desenvolvimento ou testes), a API funciona normalmente.
    # ASGI = Asynchronous Server Gateway Interface
    if frontend_dist is not None and frontend_dist.is_dir():
        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
    else:
        logger.info("frontend/dist não encontrado: servindo apenas a API")
    return app


# Instância usada pelo uvicorn.
app = create_app()
