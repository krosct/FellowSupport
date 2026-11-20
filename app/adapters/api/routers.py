"""Rotas HTTP da Etapa 0: saúde, metadados, perfis e tickets.

Os endpoints são ``def`` (síncronos) e rodam no threadpool do FastAPI (ADR 0015). Nenhuma regra de negócio mora
aqui: as rotas só traduzem HTTP para chamadas às portas do ``Container``.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.adapters.api.dto import (
    EnumsOut,
    LimitsOut,
    LlmInfoOut,
    MetaOut,
    OptionOut,
    RubricOut,
)
from app.container import Container
from app.domain import rubric
from app.domain.models import Channel, CommStyle, ContentType, CustomerProfile, TechLevel, Ticket

health_router = APIRouter(tags=["saúde"])
api_router = APIRouter(prefix="/api")


def get_container(request: Request) -> Container:
    """Dependência: entrega o ``Container`` guardado em ``app.state`` pela fábrica da aplicação."""
    return request.app.state.container


ContainerDep = Annotated[Container, Depends(get_container)]


def _options(enum_cls: type[StrEnum]) -> list[OptionOut]:
    """Converte um enum em lista ``{value, label}`` preservando a ordem de declaração."""
    return [OptionOut(value=item.value, label=item.label) for item in enum_cls]  # type: ignore[attr-defined]


@health_router.get("/healthz")
def healthz() -> dict[str, str]:
    """Verificação de saúde, usada pelo deploy e por monitoramento."""
    return {"status": "ok"}


@api_router.get("/meta", response_model=MetaOut, tags=["metadados"])
def meta(container: ContainerDep) -> MetaOut:
    """Enums, tipos de conteúdo, rubrica e versão padrão: a fonte única de rótulos do front-end.

    Expõe apenas dados públicos: provedor e modelo, nunca a chave nem a URL do provedor.
    """
    settings = container.settings
    return MetaOut(
        enums=EnumsOut(
            tech_level=_options(TechLevel), comm_style=_options(CommStyle), channel=_options(Channel)
        ),
        content_types=_options(ContentType),
        rubric=RubricOut.model_validate(rubric.rubric_as_dict()),
        default_prompt_version=settings.default_prompt_version,
        limits=LimitsOut(max_ticket_chars=settings.max_ticket_chars),
        llm=LlmInfoOut(provider=settings.llm_provider, model=settings.llm_model),
    )


@api_router.get("/profiles", response_model=list[CustomerProfile], tags=["catálogo"])
def list_profiles(container: ContainerDep) -> list[CustomerProfile]:
    """Perfis de cliente do catálogo."""
    return container.profiles.list_all()


@api_router.get("/tickets", response_model=list[Ticket], tags=["catálogo"])
def list_tickets(container: ContainerDep) -> list[Ticket]:
    """Tickets de exemplo do catálogo."""
    return container.tickets.list_all()
