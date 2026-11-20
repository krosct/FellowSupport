"""Casos de uso de geração de conteúdo (ADR 0007): o núcleo ``_generate`` e uma função pública por tipo.

Fluxo de ``_generate``: monta as mensagens com o motor de prompts, calcula a chave de cache e, se houver execução
equivalente, grava uma nova execução com ``cache_hit: true`` sem chamar o LLM (ADR 0010 e 0028). Sem acerto, chama
o LLM, valida a saída com o schema Pydantic do tipo e com as restrições do canal, faz **uma** tentativa de reparo
se a validação falhar (ADR 0004) e persiste a execução em um arquivo JSON (ADR 0009), inclusive quando dá erro
(``status: "error"``, que nunca entra no cache). No fluxograma, o ASCII é desenhado por código e vai em
``rendered`` (ADR 0008).

``generate_all`` roda os quatro tipos em paralelo com ``ThreadPoolExecutor`` (ADR 0007 e 0015): cada tipo grava
a própria execução e a falha de um não derruba os outros.

Este módulo não conhece FastAPI, SDK nem disco: só portas e domínio. Quem liga os adaptadores é o ``container``.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ValidationError

from app.domain.cache_key import compute_cache_key
from app.domain.channel_rules import find_channel_violations
from app.domain.errors import DomainError, InvalidLLMOutput, NotFound, ValidationFailed
from app.domain.flow_render import render_flow
from app.domain.llm_output import format_validation_error
from app.domain.models import (
    FREE_TICKET_TITLE,
    OUTPUT_SCHEMAS,
    RUN_ID_LENGTH,
    CacheEntry,
    ContentType,
    CustomerProfile,
    FlowSummary,
    RunError,
    RunParams,
    RunRecord,
    RunTicket,
)
from app.domain.prompting.engine import PromptBuilder
from app.domain.prompting.registry import PromptRegistry
from app.ports.llm import ChatMessage, LLMClient, LLMParams, LLMResult, ReasoningMode, StructuredMode
from app.ports.repositories import CacheStore, ProfileRepo, RunRepo, TicketRepo

logger = logging.getLogger("fellowsupport.generators")

# Número máximo de chamadas ao LLM por geração: a original e uma de reparo (ADR 0004).
MAX_ATTEMPTS = 2


@dataclass(frozen=True)
class GenerationConfig:
    """Parte da configuração de que a geração precisa (o ``container`` a monta a partir do ``Settings``).

    Existe para o serviço não depender de ``pydantic-settings`` e para os testes montarem o cenário sem ``.env``.
    """

    provider: str
    model: str
    temperature: float
    max_tokens: int
    structured_mode: StructuredMode
    reasoning: ReasoningMode
    default_prompt_version: str
    max_ticket_chars: int
    save_prompt_messages: bool
    timezone: str
    cache_enabled: bool = True  # interruptor geral (CACHE_ENABLED); cada chamada ainda pode desligar com use_cache


def _system_clock(tz: ZoneInfo) -> datetime:
    """Relógio real no fuso pedido. Os testes injetam um relógio fixo."""
    return datetime.now(tz)


@dataclass(frozen=True)
class GenerationContext:
    """Dependências da geração, todas atrás de portas (ADR 0002)."""

    llm: LLMClient
    prompts: PromptBuilder
    registry: PromptRegistry
    runs: RunRepo
    cache: CacheStore
    profiles: ProfileRepo
    tickets: TicketRepo
    config: GenerationConfig
    clock: Callable[[ZoneInfo], datetime] = field(default=_system_clock)


@dataclass(frozen=True)
class GenerationResult:
    """Resultado de uma geração: o registro completo e o caminho do JSON salvo.

    ``exception`` só vem preenchida internamente, quando a execução gravada tem ``status: "error"``: permite que
    ``generate_all`` mostre o erro **e** o caminho do JSON de erro, enquanto os geradores individuais continuam
    levantando a exceção para o chamador.
    """

    record: RunRecord
    saved_path: str
    exception: DomainError | None = field(default=None, compare=False, repr=False)


@dataclass
class _Tally:
    """Contabilidade das chamadas ao LLM de uma geração, atualizada a cada chamada.

    Fica fora do retorno de ``_call_with_repair`` para o registro de erro também levar o que já foi gasto
    (tentativas, tokens e modelo) quando a segunda chamada falha.
    """

    attempts: int = 0
    usage: dict[str, int] = field(default_factory=dict)
    model_used: str | None = None

    def add(self, result: LLMResult) -> None:
        """Soma uma chamada concluída."""
        self.attempts += 1
        self.model_used = result.model_used or self.model_used
        for key, value in result.usage.items():
            self.usage[key] = self.usage.get(key, 0) + value


# Verificação extra da saída já válida pelo schema (hoje: restrições do canal). Devolve o problema ou "".
OutputCheck = Callable[[BaseModel], str]


def _validate(schema: type[BaseModel], result: LLMResult, extra_check: OutputCheck) -> tuple[BaseModel | None, str]:
    """Valida a resposta contra o schema e a verificação extra. Devolve ``(saída, "")`` ou
    ``(None, descrição do problema)``; o problema volta ao modelo no reparo."""
    if result.parsed is None:
        return None, "A resposta não contém um objeto JSON válido."
    try:
        output = schema.model_validate(result.parsed)
    except ValidationError as exc:
        return None, format_validation_error(exc)
    problem = extra_check(output)
    return (None, problem) if problem else (output, "")


def _call_with_repair(
    ctx: GenerationContext,
    version: str,
    messages: list[ChatMessage],
    schema: type[BaseModel],
    params: LLMParams,
    tally: _Tally,
    extra_check: OutputCheck,
) -> BaseModel:
    """Chama o LLM e valida; se a saída for inválida, faz uma única tentativa de reparo (ADR 0004).

    Levanta ``InvalidLLMOutput`` se a saída continuar inválida; erros do provedor (``LLMUnavailable`` e
    ``LLMRateLimited``) sobem como estão.
    """
    result = ctx.llm.complete(messages, schema, params)
    tally.add(result)
    output, problem = _validate(schema, result, extra_check)
    if output is not None:
        return output

    logger.warning("Saída inválida na 1ª tentativa; tentando reparo (%s)", problem.splitlines()[0])
    repair_messages = ctx.prompts.build_repair(version, messages, result.text, problem)
    result = ctx.llm.complete(repair_messages, schema, params)
    tally.add(result)
    output, problem = _validate(schema, result, extra_check)
    if output is None:
        raise InvalidLLMOutput(f"O modelo não devolveu uma saída válida, mesmo após o reparo:\n{problem}")
    return output


def _check_input(ctx: GenerationContext, ticket: RunTicket, version: str) -> None:
    """Valida a entrada antes de gastar uma chamada: ticket vazio ou grande demais e versão inexistente.

    Separada para ``generate_all`` falhar uma vez só, em vez de repetir o mesmo erro nos quatro tipos.
    """
    if not ticket.text.strip():
        raise ValidationFailed("O texto do ticket está vazio.")
    if len(ticket.text) > ctx.config.max_ticket_chars:
        raise ValidationFailed(
            f"O texto do ticket tem {len(ticket.text)} caracteres; o limite é {ctx.config.max_ticket_chars}."
        )
    ctx.registry.get(version)  # NotFound se a versão não existir


def _find_cached_source(ctx: GenerationContext, key: str) -> RunRecord | None:
    """Execução de origem do cache para ``key``, ou ``None`` se não houver acerto utilizável.

    Só vale como acerto uma origem que ainda existe, terminou com sucesso e tem saída. Ponteiro órfão (execução
    apagada) ou apontando para um registro de erro é tratado como "não achei": a geração segue normalmente e,
    ao terminar com sucesso, regrava o ponteiro, o que cura o cache sozinho.
    """
    entry = ctx.cache.get(key)
    if entry is None:
        return None
    try:
        source = ctx.runs.get(entry.source_run_id).record
    except NotFound:
        logger.warning("cache %s aponta para a execução %s, que não existe mais", key[:12], entry.source_run_id)
        return None
    if source.status != "ok" or source.output is None:
        return None
    return source


def _generate_result(
    ctx: GenerationContext,
    content_type: ContentType,
    profile: CustomerProfile,
    ticket: RunTicket,
    prompt_version: str | None,
    use_cache: bool = True,
) -> GenerationResult:
    """Núcleo comum aos geradores: monta, consulta o cache, chama, valida, repara se preciso e persiste.

    Erros de entrada (ticket grande demais, versão inexistente) levantam antes de qualquer chamada e **não**
    geram registro. Erros do LLM e saída inválida geram um registro ``status: "error"``, devolvido em
    ``GenerationResult.exception`` (ver ``_generate`` para a variante que levanta) e nunca entram no cache.

    O cache só atua quando ``CACHE_ENABLED`` e ``use_cache`` estão ligados; desligado, não lê **nem grava**
    (ADR 0028). A ``cache_key`` vai no registro de qualquer forma, para localizar execuções equivalentes.
    """
    config = ctx.config
    version = prompt_version or config.default_prompt_version

    # --- Validação de entrada: falha antes de gastar uma chamada ao LLM -------------------------
    _check_input(ctx, ticket, version)
    messages = ctx.prompts.build(version, content_type, profile, ticket.text)
    schema = OUTPUT_SCHEMAS[content_type]
    params = LLMParams(
        model=config.model,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        structured_mode=config.structured_mode,
        reasoning=config.reasoning,
    )
    prompt_sha256 = ctx.registry.actual_sha256(version)
    cache_key = compute_cache_key(
        profile=profile,
        ticket_text=ticket.text,
        content_type=content_type,
        prompt_version=version,
        prompt_sha256=prompt_sha256,
        provider=config.provider,
        model=config.model,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        structured_mode=config.structured_mode,
        reasoning=config.reasoning,
    )
    caching = config.cache_enabled and use_cache
    started = time.perf_counter()

    def make_record(**variable: object) -> RunRecord:
        """Registro com os campos comuns a acerto, sucesso e erro; ``variable`` traz o que muda em cada caso."""
        return RunRecord(
            run_id=uuid.uuid4().hex[:RUN_ID_LENGTH],
            timestamp=ctx.clock(ZoneInfo(config.timezone)).isoformat(timespec="seconds"),
            customer_id=profile.id,
            customer_profile=profile,
            ticket=ticket,
            content_type=content_type,
            prompt_version=version,
            prompt_sha256=prompt_sha256,
            provider=config.provider,
            model=config.model,
            params=RunParams(
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                structured_mode=config.structured_mode,
                reasoning=config.reasoning,
            ),
            cache_key=cache_key,
            prompt_messages=[dict(m) for m in messages] if config.save_prompt_messages else [],
            **variable,
        )

    # --- Cache: acerto grava uma nova execução (evidência do reaproveitamento) e não chama o LLM ---
    source = _find_cached_source(ctx, cache_key) if caching else None
    if source is not None:
        record = make_record(
            status="ok",
            model_used=source.model_used,  # o modelo que de fato produziu a saída reaproveitada
            cache_hit=True,
            source_run_id=source.run_id,
            attempts=0,  # nenhuma chamada ao LLM
            latency_ms=int((time.perf_counter() - started) * 1000),  # só o tempo de ler o cache (~0 ms)
            usage={},  # nenhum token gasto agora
            output=source.output,
            rendered=source.rendered,
        )
        saved_path = ctx.runs.save(record)
        logger.info(
            "execução %s: tipo=%s versão=%s cache hit (origem %s) latência=%dms",
            record.run_id, content_type.value, version, source.run_id, record.latency_ms,
        )
        return GenerationResult(record=record, saved_path=saved_path)

    # --- Chamada ao LLM (com reparo) e registro ------------------------------------------------
    tally = _Tally()
    error: RunError | None = None
    raised: DomainError | None = None
    output: dict | None = None
    rendered: str | None = None

    def channel_check(candidate: BaseModel) -> str:
        """Restrições de formato do canal do perfil (ex.: telefone sem markdown) sobre a saída."""
        return find_channel_violations(profile.channel, candidate)

    started = time.perf_counter()  # a latência de uma geração real não inclui a consulta ao cache
    try:
        validated = _call_with_repair(ctx, version, messages, schema, params, tally, channel_check)
        output = validated.model_dump(mode="json")
        renderer = _RENDERERS.get(content_type)
        rendered = renderer(validated) if renderer else None
    except DomainError as exc:
        error, raised = RunError(type=type(exc).__name__, message=str(exc)), exc
    latency_ms = int((time.perf_counter() - started) * 1000)

    record = make_record(
        status="error" if error else "ok",
        model_used=tally.model_used,
        attempts=max(tally.attempts, 1),
        latency_ms=latency_ms,
        usage=tally.usage,
        output=output,
        rendered=rendered,
        error=error,
    )
    saved_path = ctx.runs.save(record)
    # O ponteiro do cache só nasce depois de a execução estar gravada (nunca aponta para o vazio) e só para
    # sucesso: erros nunca entram no cache (ADR 0018).
    if caching and record.status == "ok":
        ctx.cache.put(CacheEntry(cache_key=cache_key, source_run_id=record.run_id, created_at=record.timestamp))
    # Nível INFO sem o texto do ticket (ADR 0019).
    logger.info(
        "execução %s: tipo=%s versão=%s status=%s modelo=%s latência=%dms tentativas=%d",
        record.run_id, content_type.value, version, record.status, record.model_used, latency_ms, record.attempts,
    )
    return GenerationResult(record=record, saved_path=saved_path, exception=raised)


def _generate(
    ctx: GenerationContext,
    content_type: ContentType,
    profile: CustomerProfile,
    ticket: RunTicket,
    prompt_version: str | None,
    use_cache: bool = True,
) -> GenerationResult:
    """Como ``_generate_result``, mas levanta a exceção do domínio quando a execução terminou em erro.

    A execução com erro já foi gravada antes de a exceção subir.
    """
    result = _generate_result(ctx, content_type, profile, ticket, prompt_version, use_cache)
    if result.exception is not None:
        raise result.exception
    return result


# Desenho determinístico de saídas visuais (ADR 0008): tipo -> função que transforma a saída validada em texto.
_RENDERERS: dict[ContentType, Callable[[BaseModel], str]] = {
    ContentType.FLOW_SUMMARY: lambda output: render_flow(FlowSummary.model_validate(output.model_dump())),
}


def generate_diagnosis(
    ctx: GenerationContext,
    profile: CustomerProfile,
    ticket: RunTicket,
    prompt_version: str | None = None,
    use_cache: bool = True,
) -> GenerationResult:
    """Gera o diagnóstico (hipóteses, evidências, faltantes e conclusão) do ticket para o perfil."""
    return _generate(ctx, ContentType.DIAGNOSIS, profile, ticket, prompt_version, use_cache)


def generate_resolution_steps(
    ctx: GenerationContext,
    profile: CustomerProfile,
    ticket: RunTicket,
    prompt_version: str | None = None,
    use_cache: bool = True,
) -> GenerationResult:
    """Gera o passo a passo de resolução (passos verificáveis, escalonamento e fechamento) adaptado ao perfil."""
    return _generate(ctx, ContentType.RESOLUTION_STEPS, profile, ticket, prompt_version, use_cache)


def generate_clarifying_questions(
    ctx: GenerationContext,
    profile: CustomerProfile,
    ticket: RunTicket,
    prompt_version: str | None = None,
    use_cache: bool = True,
) -> GenerationResult:
    """Gera as perguntas de esclarecimento priorizadas (3 a 5), com motivo e o que cada resposta destrava."""
    return _generate(ctx, ContentType.CLARIFYING_QUESTIONS, profile, ticket, prompt_version, use_cache)


def generate_flow_summary(
    ctx: GenerationContext,
    profile: CustomerProfile,
    ticket: RunTicket,
    prompt_version: str | None = None,
    use_cache: bool = True,
) -> GenerationResult:
    """Gera o resumo do fluxo como árvore de decisão; o ASCII é desenhado por código e vai em ``rendered``."""
    return _generate(ctx, ContentType.FLOW_SUMMARY, profile, ticket, prompt_version, use_cache)


# Tipo de conteúdo -> gerador público. A ordem de declaração é a ordem de exibição do modo ``all``.
_GENERATORS: dict[ContentType, Callable[..., GenerationResult]] = {
    ContentType.DIAGNOSIS: generate_diagnosis,
    ContentType.RESOLUTION_STEPS: generate_resolution_steps,
    ContentType.CLARIFYING_QUESTIONS: generate_clarifying_questions,
    ContentType.FLOW_SUMMARY: generate_flow_summary,
}


def _resolve_scenario(
    ctx: GenerationContext, profile_id: str, ticket_id: str | None, ticket_text: str | None
) -> tuple[CustomerProfile, RunTicket]:
    """Resolve perfil e ticket (do catálogo **ou** texto livre; exatamente um dos dois)."""
    if (ticket_id is None) == (ticket_text is None):
        raise ValidationFailed("Informe o ticket do catálogo (ticket_id) ou um texto livre (ticket_text), só um.")
    profile = ctx.profiles.get(profile_id)
    if ticket_id is not None:
        catalog_ticket = ctx.tickets.get(ticket_id)
        ticket = RunTicket(id=catalog_ticket.id, title=catalog_ticket.title, text=catalog_ticket.text)
    else:
        ticket = RunTicket(id=None, title=FREE_TICKET_TITLE, text=(ticket_text or "").strip())
    return profile, ticket


def generate(
    ctx: GenerationContext,
    *,
    content_type: ContentType,
    profile_id: str,
    ticket_id: str | None = None,
    ticket_text: str | None = None,
    prompt_version: str | None = None,
    use_cache: bool = True,
) -> GenerationResult:
    """Ponto de entrada único de API e CLI para um tipo: resolve perfil e ticket e chama o gerador do tipo.

    O ticket vem do catálogo (``ticket_id``) **ou** de texto livre (``ticket_text``); exatamente um dos dois.
    ``use_cache=False`` ignora o cache nesta chamada (não lê nem grava).
    """
    profile, ticket = _resolve_scenario(ctx, profile_id, ticket_id, ticket_text)
    return _GENERATORS[content_type](ctx, profile, ticket, prompt_version, use_cache)


@dataclass(frozen=True)
class BatchItem:
    """Desfecho de um tipo no modo ``all``: a execução gravada (com ou sem erro) e/ou a exceção.

    ``result`` é ``None`` só quando a falha ocorreu antes de existir execução (ex.: a versão do prompt não tem o
    arquivo daquele tipo).
    """

    content_type: ContentType
    result: GenerationResult | None
    error: DomainError | None

    @property
    def ok(self) -> bool:
        """``True`` se o tipo foi gerado com sucesso."""
        return self.error is None and self.result is not None


@dataclass(frozen=True)
class BatchResult:
    """Resultado do modo ``all``: um item por tipo, na ordem de ``ContentType``."""

    items: list[BatchItem]

    @property
    def errors(self) -> list[DomainError]:
        """Exceções dos tipos que falharam, na ordem dos itens."""
        return [item.error for item in self.items if item.error is not None]


def generate_all(
    ctx: GenerationContext,
    *,
    profile_id: str,
    ticket_id: str | None = None,
    ticket_text: str | None = None,
    prompt_version: str | None = None,
    use_cache: bool = True,
) -> BatchResult:
    """Gera os quatro tipos em paralelo (ADR 0007 e 0015) e devolve um item por tipo.

    Cada tipo consulta o cache de forma independente (a chave inclui o tipo): um pode acertar e outro gerar.

    Erros de entrada (perfil, ticket ou versão inválidos) levantam **uma vez**, antes de abrir as threads. Depois
    disso, cada tipo é independente: falhas do LLM ou do schema de um tipo viram um item com erro e os outros
    seguem. Cada tipo grava o próprio arquivo de execução (nomes únicos por ``run_id``, sem corrida).
    """
    profile, ticket = _resolve_scenario(ctx, profile_id, ticket_id, ticket_text)
    _check_input(ctx, ticket, prompt_version or ctx.config.default_prompt_version)

    def run_one(content_type: ContentType) -> BatchItem:
        """Executa um tipo isolando as falhas esperadas do domínio no próprio item."""
        try:
            result = _generate_result(ctx, content_type, profile, ticket, prompt_version, use_cache)
        except DomainError as exc:  # ex.: NotFound do arquivo de prompt do tipo
            return BatchItem(content_type, None, exc)
        return BatchItem(content_type, result, result.exception)

    types = list(_GENERATORS)
    with ThreadPoolExecutor(max_workers=len(types), thread_name_prefix="gen") as pool:
        items = list(pool.map(run_one, types))  # map preserva a ordem de ``types``
    return BatchResult(items=items)
