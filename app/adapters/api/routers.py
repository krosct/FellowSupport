"""Rotas HTTP: saúde, metadados, catálogo (perfis e tickets, com CRUD), versões de prompt, geração, histórico e
comparação (com as notas da rubrica).

Os endpoints são ``def`` (síncronos) e rodam no threadpool do FastAPI (ADR 0015). Nenhuma regra de negócio mora
aqui: as rotas só traduzem HTTP para chamadas às portas do ``Container``.
"""

import hmac
from dataclasses import replace
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from app.adapters.api.dto import (
    ComparisonOut,
    ComparisonSummaryOut,
    GenerateAllOut,
    GenerateIn,
    GenerateOut,
    MetaOut,
    ProfileIn,
    PromptCreateIn,
    PromptDetailOut,
    PromptVersionOut,
    RunDetailOut,
    RunSummaryOut,
    SaveComparisonIn,
    TicketIn,
)
from app.adapters.api.ratelimit import LLM_CALL_LIMIT
from app.adapters.llm.factory import build_llm_client
from app.container import Container
from app.domain.errors import Forbidden, Unauthorized
from app.domain.models import (
    ALL_OPTION_VALUE,
    ContentType,
    CustomerProfile,
    RunStatus,
    Ticket,
)
from app.domain.prompting.registry import PromptChange
from app.ports.repositories import StoredComparison
from app.services.catalog import (
    create_profile,
    create_ticket,
    delete_profile,
    delete_ticket,
    update_profile,
    update_ticket,
)
from app.services.comparison import (
    DEFAULT_COMPARISONS_LIMIT,
    find_saved_comparison,
    get_comparison,
    list_comparisons,
    save_comparison,
    summarize_comparison,
)
from app.services.generators import GenerationContext, generate, generate_all
from app.services.history import DEFAULT_HISTORY_LIMIT, HistoryFilters, get_run, list_runs, summarize_run
from app.services.meta import build_meta
from app.services.meta import list_prompt_versions as list_prompt_version_infos
from app.services.prompts import create_prompt, delete_prompt, get_prompt

# Cabeçalho com o total de itens das listagens paginadas (``/api/runs`` e ``/api/comparisons``).
TOTAL_COUNT_HEADER = "X-Total-Count"
OPENROUTER_KEY_HEADER = "X-OpenRouter-Key"
ADMIN_KEY_HEADER = "X-Admin-Key"

health_router = APIRouter(tags=["saúde"])
api_router = APIRouter(prefix="/api")


def get_container(request: Request) -> Container:
    """Dependência: entrega o ``Container`` guardado em ``app.state`` pela fábrica da aplicação."""
    return request.app.state.container


def require_admin_key(request: Request) -> None:
    """Exige ``X-Admin-Key`` para mutações em clientes, tickets e prompts quando configurada ou em deploy."""
    settings = request.app.state.container.settings
    expected = settings.admin_api_key.get_secret_value()
    deploy_mode = bool(settings.public_url.strip())
    if not expected:
        if deploy_mode:
            raise Forbidden("Operações administrativas desabilitadas sem ADMIN_API_KEY configurada no servidor.")
        return
    provided = request.headers.get(ADMIN_KEY_HEADER, "").strip()
    if not provided or not hmac.compare_digest(provided, expected):
        raise Unauthorized("Chave administrativa ausente ou inválida. Informe admin_api_key na sessão.")


ADMIN_ONLY = [Depends(require_admin_key)]
ContainerDep = Annotated[Container, Depends(get_container)]


def _generation_context(container: Container, request: Request) -> GenerationContext:
    """Resolve o contexto de geração aplicando ``X-OpenRouter-Key`` da sessão quando informada."""
    settings = container.settings
    if settings.llm_provider == "fake":
        return container.generation
    session_key = (request.headers.get(OPENROUTER_KEY_HEADER) or "").strip()
    if session_key:
        return replace(container.generation, llm=build_llm_client(settings, api_key_override=session_key))
    if settings.public_url.strip():
        return replace(container.generation, llm=build_llm_client(settings, api_key_override=""))
    return container.generation


@health_router.get("/healthz")
def healthz() -> dict[str, str]:
    """Verificação de saúde, usada pelo deploy e por monitoramento."""
    return {"status": "ok"}


@api_router.get("/meta", response_model=MetaOut, tags=["metadados"])
def meta(container: ContainerDep) -> MetaOut:
    """Enums, tipos de conteúdo, rubrica, versão padrão e limites: a fonte única de rótulos do site e da CLI.

    Expõe apenas dados públicos: provedor e modelo, nunca a chave nem a URL do provedor.
    """
    settings = container.settings
    deploy_mode = bool(settings.public_url.strip())
    server_key_configured = bool(settings.openrouter_api_key.get_secret_value()) and not deploy_mode
    admin_protected = bool(settings.admin_api_key.get_secret_value()) or deploy_mode
    return build_meta(
        provider=settings.llm_provider,
        model=settings.llm_model,
        max_ticket_chars=settings.max_ticket_chars,
        registry=container.prompts,
        server_key_configured=server_key_configured,
        admin_protected=admin_protected,
        deploy_mode=deploy_mode,
    )


@api_router.get("/profiles", response_model=list[CustomerProfile], tags=["catálogo"])
def list_profiles(container: ContainerDep) -> list[CustomerProfile]:
    """Perfis de cliente do catálogo, na ordem de criação."""
    return container.profiles.list_all()


@api_router.post(
    "/profiles", response_model=CustomerProfile, status_code=201, tags=["catálogo"], dependencies=ADMIN_ONLY
)
def post_profile(body: ProfileIn, container: ContainerDep) -> CustomerProfile:
    """Cria um cliente no catálogo; o id é gerado pelo servidor (ADR 0037)."""
    return create_profile(container.profiles, body.name, body.tech_level, body.comm_style, body.channel)


@api_router.put("/profiles/{profile_id}", response_model=CustomerProfile, tags=["catálogo"], dependencies=ADMIN_ONLY)
def put_profile(profile_id: str, body: ProfileIn, container: ContainerDep) -> CustomerProfile:
    """Troca nome, nível, estilo e canal do cliente; o id não muda."""
    return update_profile(container.profiles, profile_id, body.name, body.tech_level, body.comm_style, body.channel)


@api_router.delete("/profiles/{profile_id}", response_model=CustomerProfile, tags=["catálogo"], dependencies=ADMIN_ONLY)
def remove_profile(profile_id: str, container: ContainerDep) -> CustomerProfile:
    """Remove o cliente e devolve o que foi removido. O histórico de execuções não é alterado."""
    return delete_profile(container.profiles, profile_id)


@api_router.get("/tickets", response_model=list[Ticket], tags=["catálogo"])
def list_tickets(container: ContainerDep) -> list[Ticket]:
    """Tickets do catálogo, na ordem de criação."""
    return container.tickets.list_all()


@api_router.post("/tickets", response_model=Ticket, status_code=201, tags=["catálogo"], dependencies=ADMIN_ONLY)
def post_ticket(body: TicketIn, container: ContainerDep) -> Ticket:
    """Cria um ticket no catálogo; o id é gerado pelo servidor (ADR 0037)."""
    return create_ticket(container.tickets, body.title, body.text, container.settings.max_ticket_chars)


@api_router.put("/tickets/{ticket_id}", response_model=Ticket, tags=["catálogo"], dependencies=ADMIN_ONLY)
def put_ticket(ticket_id: str, body: TicketIn, container: ContainerDep) -> Ticket:
    """Troca título e corpo do ticket; o id não muda."""
    return update_ticket(container.tickets, ticket_id, body.title, body.text, container.settings.max_ticket_chars)


@api_router.delete("/tickets/{ticket_id}", response_model=Ticket, tags=["catálogo"], dependencies=ADMIN_ONLY)
def remove_ticket(ticket_id: str, container: ContainerDep) -> Ticket:
    """Remove o ticket e devolve o que foi removido. O histórico de execuções não é alterado."""
    return delete_ticket(container.tickets, ticket_id)


@api_router.get("/prompt-versions", response_model=list[PromptVersionOut], tags=["prompts"])
def list_prompt_versions(container: ContainerDep) -> list[PromptVersionOut]:
    """Versões de prompt disponíveis, com o conteúdo do ``meta.json`` (mudanças, motivo e hash)."""
    return list_prompt_version_infos(container.prompts)


def _to_prompt_changes(items: list) -> list[PromptChange]:
    """Converte ``PromptChangeIn`` em ``PromptChange`` sem validar antes do serviço."""
    return [PromptChange.model_construct(what=i.what, why=i.why, expected_effect=i.expected_effect) for i in items]


@api_router.get("/prompts", response_model=list[PromptVersionOut], tags=["prompts"])
def list_prompts(container: ContainerDep) -> list[PromptVersionOut]:
    """Lista as versões de prompt disponíveis, da mais antiga para a mais nova."""
    return list_prompt_version_infos(container.prompts)


@api_router.get("/prompts/{version}", response_model=PromptDetailOut, tags=["prompts"])
def get_prompt_detail(version: str, container: ContainerDep) -> PromptDetailOut:
    """Metadados e todos os arquivos de uma versão de prompt. Versão inexistente responde 404."""
    return get_prompt(container.prompts, version)


@api_router.post("/prompts", response_model=PromptDetailOut, status_code=201, tags=["prompts"], dependencies=ADMIN_ONLY)
def post_prompt(body: PromptCreateIn, container: ContainerDep) -> PromptDetailOut:
    """Cria uma versão de prompt derivada de ``based_on``, calcula o hash e grava os arquivos."""
    return create_prompt(
        container.prompt_store,
        container.prompts,
        based_on=body.based_on,
        description=body.description,
        changes=_to_prompt_changes(body.changes),
        files=body.files,
        timezone=container.settings.app_timezone,
    )


@api_router.delete("/prompts/{version}", response_model=PromptVersionOut, tags=["prompts"], dependencies=ADMIN_ONLY)
def remove_prompt(version: str, container: ContainerDep) -> PromptVersionOut:
    """Remove a pasta e os arquivos de uma versão derivada. A versão base ``v1`` responde 422."""
    return delete_prompt(container.prompt_store, container.prompts, version)


@api_router.post(
    "/generate", response_model=GenerateOut | GenerateAllOut, tags=["geração"], dependencies=LLM_CALL_LIMIT
)
def generate_content(body: GenerateIn, request: Request, container: ContainerDep) -> GenerateOut | GenerateAllOut:
    """Gera um conteúdo (ou os quatro, com ``content_type: "all"``) e devolve a execução salva e o caminho do JSON.

    No modo ``all`` a resposta traz um item por tipo e a falha de um tipo não afeta os outros. Só se **todos**
    falharem a rota responde com o erro do primeiro (mesmo mapeamento do tipo único), porque nada foi gerado; se só
    parte falhar, ``warning`` diz quais tipos (a mesma frase que a CLI imprime).
    Com ``use_cache`` ligado (padrão), uma entrada equivalente a uma execução anterior bem-sucedida não chama o LLM:
    a resposta traz uma nova execução com ``cache_hit: true`` e ``source_run_id``. No modo ``all`` cada tipo
    consulta o cache sozinho. Com ``use_cache`` desligado, se algum tipo substituir uma entrada do cache e o corpo não
    trouxer ``confirm_replace: true``, a rota responde 409 com **todas** as entradas afetadas e não gera nada
    (ADR 0036).
    Erros do domínio viram HTTP pelo tratador único de ``main.py``: 404, 409, 422, 429, 502 e 503.
    Além disso, o limite de taxa por IP (``RATE_LIMIT_PER_MIN``) responde 429 com ``Retry-After``.
    """
    gen_ctx = _generation_context(container, request)
    # Se pediu "all", gera os quatro tipos em paralelo; falha só se todos errarem.
    if body.content_type == ALL_OPTION_VALUE:
        batch = generate_all(
            gen_ctx,
            profile_id=body.profile_id,
            ticket_id=body.ticket_id,
            prompt_version=body.prompt_version,
            use_cache=body.use_cache,
            confirm_replace=body.confirm_replace,
        )
        batch.raise_if_all_failed()
        return batch.to_payload()
    result = generate(
        gen_ctx,
        content_type=ContentType(body.content_type),
        profile_id=body.profile_id,
        ticket_id=body.ticket_id,
        prompt_version=body.prompt_version,
        use_cache=body.use_cache,
        confirm_replace=body.confirm_replace,
    )
    return GenerateOut(saved_path=result.saved_path, run=result.record)


@api_router.get("/runs", response_model=list[RunSummaryOut], tags=["histórico"])
def list_history(
    container: ContainerDep,
    response: Response,
    customer_id: str | None = None,
    ticket_id: str | None = None,
    content_type: ContentType | None = None,
    prompt_version: str | None = None,
    status: RunStatus | None = None,
    cache_key: str | None = None,
    limit: int = DEFAULT_HISTORY_LIMIT,
    offset: int = 0,
) -> list[RunSummaryOut]:
    """Uma página do histórico de execuções, da mais recente para a mais antiga, com filtros opcionais.

    ``limit`` e ``offset`` escolhem a página; o total que casa com os filtros vai no cabeçalho ``X-Total-Count``.
    ``cache_key`` (inteira ou só o começo) localiza execuções equivalentes: as que compartilham a mesma chave de
    cache. Valores desconhecidos de ``content_type`` e ``status``, limite fora de 1 a 500 e ``offset`` negativo
    respondem 422.
    """
    # Monta os filtros da query e devolve apenas o resumo de cada execução.
    filters = HistoryFilters(
        customer_id=customer_id,
        ticket_id=ticket_id,
        content_type=content_type,
        prompt_version=prompt_version,
        status=status,
        cache_key=cache_key,
    )
    page = list_runs(container.runs, filters, limit, offset)
    response.headers[TOTAL_COUNT_HEADER] = str(page.total)
    return [summarize_run(stored) for stored in page.items]


@api_router.get("/runs/{run_id}", response_model=RunDetailOut, tags=["histórico"])
def get_history_run(run_id: str, container: ContainerDep) -> RunDetailOut:
    """Detalhe de uma execução (registro completo e caminho do JSON). Id inexistente ou malformado: 404."""
    stored = get_run(container.runs, run_id)
    return RunDetailOut(saved_path=stored.saved_path, run=stored.record)


def _comparison_out(stored: StoredComparison) -> ComparisonOut:
    """Comparação lida do disco no formato da API."""
    return ComparisonOut(saved_path=stored.saved_path, comparison=stored.record)


@api_router.post("/comparisons", response_model=ComparisonOut, tags=["comparação"])
def post_comparison(body: SaveComparisonIn, container: ContainerDep) -> ComparisonOut:
    """Salva a comparação das execuções com as notas do candidato, o vencedor e a conclusão.

    Comparar não gera nada: as execuções já existem (ADR 0040). Grava as avaliações nas execuções e o arquivo
    ``var/comparisons/<id>.json``. Avaliação faltando em alguma execução, nota fora de 1 a 5, execuções de cenários
    diferentes, da mesma versão ou vindas do cache respondem 422; execução inexistente, 404.
    """
    stored = save_comparison(
        container.comparison, run_ids=body.run_ids, evaluations=body.evaluations, conclusion=body.conclusion
    )
    return _comparison_out(stored)


@api_router.get("/comparisons", response_model=list[ComparisonSummaryOut], tags=["comparação"])
def list_saved_comparisons(
    container: ContainerDep, response: Response, limit: int = DEFAULT_COMPARISONS_LIMIT, offset: int = 0
) -> list[ComparisonSummaryOut]:
    """Uma página das comparações salvas, da mais recente para a mais antiga, com o total em ``X-Total-Count``.

    Limite fora de 1 a 500 ou ``offset`` negativo respondem 422.
    """
    page = list_comparisons(container.comparisons, limit, offset)
    response.headers[TOTAL_COUNT_HEADER] = str(page.total)
    return [summarize_comparison(item) for item in page.items]


@api_router.get("/comparisons/lookup", response_model=ComparisonOut | None, tags=["comparação"])
def lookup_saved_comparison(
    container: ContainerDep, run_ids: Annotated[list[str], Query(description="Execuções comparadas (2 ou mais).")]
) -> ComparisonOut | None:
    """Cache das comparações (ADR 0038): a comparação mais recente já salva dessas execuções, ou ``null``.

    Só lê ``var/comparisons/``; não gera nada nem consulta o LLM. Menos de 2 execuções ou ids repetidos respondem 422.
    A rota vem antes de ``/comparisons/{comparison_id}`` para ``lookup`` não ser lido como id.
    """
    found = find_saved_comparison(container.comparisons, run_ids)
    return _comparison_out(found) if found else None


@api_router.get("/comparisons/{comparison_id}", response_model=ComparisonOut, tags=["comparação"])
def get_saved_comparison(comparison_id: str, container: ContainerDep) -> ComparisonOut:
    """Comparação completa (cenário, saídas, avaliações, totais, vencedor e conclusão). Id inexistente: 404."""
    return _comparison_out(get_comparison(container.comparisons, comparison_id))
