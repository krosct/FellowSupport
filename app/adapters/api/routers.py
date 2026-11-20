"""Rotas HTTP: saúde, metadados, perfis, tickets, versões de prompt, geração de conteúdo e histórico.

Os endpoints são ``def`` (síncronos) e rodam no threadpool do FastAPI (ADR 0015). Nenhuma regra de negócio mora
aqui: as rotas só traduzem HTTP para chamadas às portas do ``Container``.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.adapters.api.dto import (
    EnumsOut,
    GenerateAllOut,
    GenerateIn,
    GenerateItemOut,
    GenerateOut,
    LimitsOut,
    LlmInfoOut,
    MetaOut,
    OptionOut,
    PromptVersionOut,
    RubricOut,
    RunDetailOut,
    RunSummaryOut,
)
from app.container import Container
from app.domain import rubric
from app.domain.models import (
    ALL_OPTION_LABEL,
    ALL_OPTION_VALUE,
    FREE_TICKET_TITLE,
    Channel,
    CommStyle,
    Confidence,
    ContentType,
    CustomerProfile,
    RunError,
    RunStatus,
    TechLevel,
    Ticket,
)
from app.ports.repositories import StoredRun
from app.services.generators import BatchResult, generate, generate_all
from app.services.history import DEFAULT_HISTORY_LIMIT, HistoryFilters, get_run, list_runs

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
        all_option=OptionOut(value=ALL_OPTION_VALUE, label=ALL_OPTION_LABEL),
        confidence_levels=_options(Confidence),
        rubric=RubricOut.model_validate(rubric.rubric_as_dict()),
        default_prompt_version=settings.default_prompt_version,
        free_ticket_title=FREE_TICKET_TITLE,
        limits=LimitsOut(max_ticket_chars=settings.max_ticket_chars, history_limit=DEFAULT_HISTORY_LIMIT),
        llm=LlmInfoOut(provider=settings.llm_provider, model=settings.llm_model),
        cache_enabled=settings.cache_enabled,
    )


@api_router.get("/profiles", response_model=list[CustomerProfile], tags=["catálogo"])
def list_profiles(container: ContainerDep) -> list[CustomerProfile]:
    """Perfis de cliente do catálogo."""
    return container.profiles.list_all()


@api_router.get("/tickets", response_model=list[Ticket], tags=["catálogo"])
def list_tickets(container: ContainerDep) -> list[Ticket]:
    """Tickets de exemplo do catálogo."""
    return container.tickets.list_all()


@api_router.get("/prompt-versions", response_model=list[PromptVersionOut], tags=["prompts"])
def list_prompt_versions(container: ContainerDep) -> list[PromptVersionOut]:
    """Versões de prompt disponíveis, com o conteúdo do ``meta.json`` (mudanças, motivo e hash)."""
    default = container.settings.default_prompt_version
    return [
        PromptVersionOut(**version.model_dump(), is_default=version.version == default)
        for version in container.prompts.versions()
    ]


def _batch_out(batch: BatchResult) -> GenerateAllOut:
    """Converte o resultado do modo ``all`` no formato da API, com sucesso ou erro por tipo."""
    results = []
    for item in batch.items:
        if item.ok:
            results.append(GenerateItemOut(
                content_type=item.content_type, saved_path=item.result.saved_path, run=item.result.record
            ))
            continue
        error = RunError(type=type(item.error).__name__, message=str(item.error))
        results.append(GenerateItemOut(
            content_type=item.content_type,
            saved_path=item.result.saved_path if item.result else None,
            run=item.result.record if item.result else None,
            error=error,
        ))
    return GenerateAllOut(results=results)


@api_router.post("/generate", response_model=GenerateOut | GenerateAllOut, tags=["geração"])
def generate_content(body: GenerateIn, container: ContainerDep) -> GenerateOut | GenerateAllOut:
    """Gera um conteúdo (ou os quatro, com ``content_type: "all"``) e devolve a execução salva e o caminho do JSON.

    No modo ``all`` a resposta traz um item por tipo e a falha de um tipo não afeta os outros. Só se **todos**
    falharem a rota responde com o erro do primeiro (mesmo mapeamento do tipo único), porque nada foi gerado.
    Com ``use_cache`` ligado (padrão), uma entrada equivalente a uma execução anterior bem-sucedida não chama o LLM:
    a resposta traz uma nova execução com ``cache_hit: true`` e ``source_run_id``. No modo ``all`` cada tipo
    consulta o cache sozinho. Erros do domínio viram HTTP pelo tratador único de ``main.py``: 404, 422, 429, 502 e 503.
    """
    if body.content_type == ALL_OPTION_VALUE:
        batch = generate_all(
            container.generation,
            profile_id=body.profile_id,
            ticket_id=body.ticket_id,
            ticket_text=body.ticket_text,
            prompt_version=body.prompt_version,
            use_cache=body.use_cache,
        )
        if len(batch.errors) == len(batch.items):
            raise batch.errors[0]
        return _batch_out(batch)
    result = generate(
        container.generation,
        content_type=ContentType(body.content_type),
        profile_id=body.profile_id,
        ticket_id=body.ticket_id,
        ticket_text=body.ticket_text,
        prompt_version=body.prompt_version,
        use_cache=body.use_cache,
    )
    return GenerateOut(saved_path=result.saved_path, run=result.record)


def _summary(stored: StoredRun) -> RunSummaryOut:
    """Converte uma execução lida do disco na linha enxuta da listagem."""
    run = stored.record
    return RunSummaryOut(
        run_id=run.run_id,
        timestamp=run.timestamp,
        status=run.status,
        customer_id=run.customer_id,
        customer_name=run.customer_profile.name,
        ticket_id=run.ticket.id,
        ticket_title=run.ticket.title,
        content_type=run.content_type,
        prompt_version=run.prompt_version,
        provider=run.provider,
        model=run.model,
        model_used=run.model_used,
        cache_key=run.cache_key,
        cache_hit=run.cache_hit,
        source_run_id=run.source_run_id,
        attempts=run.attempts,
        latency_ms=run.latency_ms,
        error=run.error,
        saved_path=stored.saved_path,
    )


@api_router.get("/runs", response_model=list[RunSummaryOut], tags=["histórico"])
def list_history(
    container: ContainerDep,
    customer_id: str | None = None,
    ticket_id: str | None = None,
    content_type: ContentType | None = None,
    prompt_version: str | None = None,
    status: RunStatus | None = None,
    cache_key: str | None = None,
    limit: int = DEFAULT_HISTORY_LIMIT,
) -> list[RunSummaryOut]:
    """Histórico de execuções, da mais recente para a mais antiga, com filtros opcionais e um limite.

    ``cache_key`` (inteira ou só o começo) localiza execuções equivalentes: as que compartilham a mesma chave de
    cache. Valores desconhecidos de ``content_type`` e ``status`` e limite fora de 1 a 500 respondem 422.
    """
    filters = HistoryFilters(
        customer_id=customer_id,
        ticket_id=ticket_id,
        content_type=content_type,
        prompt_version=prompt_version,
        status=status,
        cache_key=cache_key,
    )
    return [_summary(stored) for stored in list_runs(container.runs, filters, limit)]


@api_router.get("/runs/{run_id}", response_model=RunDetailOut, tags=["histórico"])
def get_history_run(run_id: str, container: ContainerDep) -> RunDetailOut:
    """Detalhe de uma execução (registro completo e caminho do JSON). Id inexistente ou malformado: 404."""
    stored = get_run(container.runs, run_id)
    return RunDetailOut(saved_path=stored.saved_path, run=stored.record)
