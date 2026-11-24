"""Casos de uso de geração de conteúdo (ADR 0007): o núcleo ``_generate`` e uma função pública por tipo.

Fluxo de ``_generate``: monta as mensagens com o motor de prompts, calcula a chave de cache e, se houver execução
equivalente, grava uma nova execução com ``cache_hit: true`` sem chamar o LLM (ADR 0010 e 0028). Sem acerto, chama
o LLM, valida a saída com o schema Pydantic do tipo e com as restrições do canal, faz **uma** tentativa de reparo
se a validação falhar (ADR 0004) e persiste a execução em um arquivo JSON (ADR 0009), inclusive quando dá erro
(``status: "error"``, que nunca entra no cache). Toda geração bem-sucedida vira a origem do cache da sua chave,
com ``use_cache`` ligado ou não (ADR 0035): ``use_cache`` só decide se o cache é **consultado** antes de gerar.
No fluxograma, o ASCII é desenhado por código e vai em ``rendered`` (ADR 0008).

``generate_all`` roda os quatro tipos em paralelo com ``ThreadPoolExecutor`` (ADR 0007 e 0015): cada tipo grava
a própria execução e a falha de um não derruba os outros.

Observabilidade (ADR 0043): cada geração (acerto de cache, sucesso ou erro) emite um evento ``generation`` com o
detalhe de cada chamada ao LLM, e o modo ``all`` emite ainda um ``generation_batch`` que liga os quatro pelo
``batch_id``.

Este módulo não conhece FastAPI, SDK nem disco: só portas e domínio. Quem liga os adaptadores é o ``container``.
"""

import logging
import threading
import time
import uuid
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ValidationError

from app.domain.cache_key import compute_cache_key
from app.domain.channel_rules import find_channel_violations
from app.domain.errors import CacheReplaceRequired, DomainError, InvalidLLMOutput, NotFound, ValidationFailed
from app.domain.flow_render import render_flow
from app.domain.llm_output import FINISH_REASON_LENGTH, format_validation_error, truncation_message
from app.domain.models import (
    OUTPUT_SCHEMAS,
    RUN_ID_LENGTH,
    CacheConflict,
    CacheEntry,
    ContentType,
    CustomerProfile,
    FlowSummary,
    LlmCall,
    RunError,
    RunParams,
    RunRecord,
    RunTicket,
)
from app.domain.prompting.engine import PromptBuilder
from app.domain.prompting.registry import PromptRegistry
from app.ports.events import EVENT_GENERATION, EVENT_GENERATION_BATCH, NULL_EVENT_LOG, EventLog
from app.ports.llm import ChatMessage, LLMClient, LLMParams, LLMResult, ReasoningMode, StructuredMode
from app.ports.repositories import CacheStore, ProfileRepo, RunRepo, TicketRepo
from app.services.clock import Clock, system_clock

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
    max_ticket_chars: int
    save_prompt_messages: bool
    timezone: str


class _KeyedLockPool:
    """Pool simples de locks por chave (singleflight) para evitar gerações concorrentes idênticas."""

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}

    @contextmanager
    def acquire(self, key: str) -> Iterator[None]:
        with self._guard:
            lock = self._locks.setdefault(key, threading.Lock())
        with lock:
            yield


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
    clock: Clock = field(default=system_clock)
    inflight: _KeyedLockPool = field(default_factory=_KeyedLockPool, compare=False, repr=False)
    events: EventLog = field(default=NULL_EVENT_LOG, compare=False, repr=False)


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
    calls: list[LlmCall] = field(default_factory=list)

    def add(self, result: LLMResult, problem: str | None) -> None:
        """Soma uma chamada concluída; ``problem`` é o motivo da recusa da saída (``None`` se foi aceita)."""
        # Conta a tentativa, registra o modelo efetivo e acumula o uso de tokens.
        self.attempts += 1
        self.model_used = result.model_used or self.model_used
        for key, value in result.usage.items():
            self.usage[key] = self.usage.get(key, 0) + value
        # Guarda o detalhe da chamada: quem atendeu, por que parou e o que foi gasto (ADR 0042).
        self.calls.append(LlmCall(
            attempt=self.attempts,
            model_used=result.model_used,
            provider_used=result.provider_used,
            response_id=result.response_id,
            finish_reason=result.finish_reason,
            latency_ms=result.latency_ms,
            usage=dict(result.usage),
            json_extracted=result.parsed is not None,
            problem=problem,
        ))


# Verificação extra da saída já válida pelo schema (hoje: restrições do canal). Devolve o problema ou "".
OutputCheck = Callable[[BaseModel], str]


def _validate(schema: type[BaseModel], result: LLMResult, extra_check: OutputCheck) -> tuple[BaseModel | None, str]:
    """Valida a resposta contra o schema e a verificação extra. Devolve ``(saída, "")`` ou
    ``(None, descrição do problema)``; o problema volta ao modelo no reparo."""
    # Rejeita a resposta se não houver nenhum objeto JSON extraído.
    if result.parsed is None:
        return None, "A resposta não contém um objeto JSON válido."
    # Valida a estrutura e os tipos da resposta contra o schema Pydantic.
    try:
        output = schema.model_validate(result.parsed)
    except ValidationError as exc:
        return None, format_validation_error(exc)
    # Verifica regras extras do canal (ex.: proibição de markdown no telefone).
    problem = extra_check(output)
    return (None, problem) if problem else (output, "")


def _attempt(
    ctx: GenerationContext,
    messages: list[ChatMessage],
    schema: type[BaseModel],
    params: LLMParams,
    tally: _Tally,
    extra_check: OutputCheck,
) -> tuple[BaseModel | None, LLMResult, str]:
    """Uma chamada ao LLM, já contabilizada no ``tally``: devolve ``(saída válida ou None, resultado, problema)``.

    Resposta cortada pelo limite de tokens e sem JSON levanta ``InvalidLLMOutput`` já com o gasto registrado: o
    reparo pediria ao mesmo modelo o mesmo tamanho de resposta (ADR 0026 e 0042).
    """
    result = ctx.llm.complete(messages, schema, params)
    if result.finish_reason == FINISH_REASON_LENGTH and result.parsed is None:
        completion = result.usage.get("completion_tokens", 0)
        message = truncation_message(
            # Sem o uso informado não dá para saber quem cortou: vale o limite configurado (o caso comum).
            max_tokens=params.max_tokens,
            completion_tokens=completion or params.max_tokens,
            reasoning_tokens=result.usage.get("reasoning_tokens", 0),
            provider=result.provider_used,
        )
        tally.add(result, message)
        logger.warning("resposta cortada (provedor=%s): %s", result.provider_used or "?", message)
        raise InvalidLLMOutput(message)
    output, problem = _validate(schema, result, extra_check)
    tally.add(result, problem or None)
    return output, result, problem


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
    # Faz a primeira tentativa e devolve logo se a saída já estiver válida.
    output, result, problem = _attempt(ctx, messages, schema, params, tally, extra_check)
    if output is not None:
        return output

    # Envia o erro de validação de volta ao modelo para uma única tentativa de reparo.
    logger.warning("Saída inválida na 1ª tentativa; tentando reparo (%s)", problem.splitlines()[0])
    repair_messages = ctx.prompts.build_repair(version, messages, result.text, problem)
    output, _, problem = _attempt(ctx, repair_messages, schema, params, tally, extra_check)
    if output is None:
        raise InvalidLLMOutput(f"O modelo não devolveu uma saída válida, mesmo após o reparo:\n{problem}")
    return output


def _resolve_version(ctx: GenerationContext, prompt_version: str | None) -> str:
    """Versão pedida ou, se nenhuma foi pedida, a mais nova do registro (a padrão)."""
    return prompt_version or ctx.registry.latest().version


def _check_input(ctx: GenerationContext, ticket: RunTicket, version: str) -> None:
    """Valida a entrada antes de gastar uma chamada: ticket vazio ou grande demais e versão inexistente.

    Separada para ``generate_all`` falhar uma vez só, em vez de repetir o mesmo erro nos quatro tipos.
    """
    # Barra ticket vazio, texto acima do limite e versão de prompt inexistente.
    if not ticket.text.strip():
        raise ValidationFailed("O texto do ticket está vazio.")
    if len(ticket.text) > ctx.config.max_ticket_chars:
        raise ValidationFailed(
            f"O texto do ticket tem {len(ticket.text)} caracteres; o limite é {ctx.config.max_ticket_chars}."
        )
    ctx.registry.get(version)  # NotFound se a versão não existir


def _cache_key(
    config: GenerationConfig,
    content_type: ContentType,
    profile: CustomerProfile,
    ticket: RunTicket,
    version: str,
    prompt_sha256: str,
) -> str:
    """Chave de cache da geração descrita pelos argumentos (única definição: geração e checagem usam a mesma)."""
    return compute_cache_key(
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


def _find_cached_source(ctx: GenerationContext, key: str) -> RunRecord | None:
    """Execução de origem do cache para ``key``, ou ``None`` se não houver acerto utilizável.

    Só vale como acerto uma origem que ainda existe, terminou com sucesso e tem saída. Ponteiro órfão (execução
    apagada) ou apontando para um registro de erro é tratado como "não achei": a geração segue normalmente e,
    ao terminar com sucesso, regrava o ponteiro, o que cura o cache sozinho.
    """
    # Procura o ponteiro no cache e tenta carregar a execução de origem.
    entry = ctx.cache.get(key)
    if entry is None:
        return None
    try:
        source = ctx.runs.get(entry.source_run_id).record
    except NotFound:
        logger.warning("cache %s aponta para a execução %s, que não existe mais", key[:12], entry.source_run_id)
        return None
    # Descarta o cache se a execução original terminou em erro ou sem saída.
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
    batch_id: str | None = None,
) -> GenerationResult:
    """Núcleo comum aos geradores: monta, consulta o cache, chama, valida, repara se preciso e persiste.

    Erros de entrada (ticket grande demais, versão inexistente) levantam antes de qualquer chamada e **não**
    geram registro. Erros do LLM e saída inválida geram um registro ``status: "error"``, devolvido em
    ``GenerationResult.exception`` (ver ``_generate`` para a variante que levanta) e nunca entram no cache.

    ``use_cache`` decide só a **leitura**: ligado, uma execução equivalente bem-sucedida é reaproveitada; desligado,
    sempre gera. A **gravação** é incondicional: toda geração que chamou o LLM e deu certo passa a ser a origem do
    cache da sua chave (ADR 0035). Um acerto não regrava o ponteiro. A ``cache_key`` vai em todo registro.

    Toda execução gravada também vira um evento ``generation`` no log (ADR 0043); ``batch_id`` liga as do modo
    ``all``.
    """
    config = ctx.config
    version = _resolve_version(ctx, prompt_version)

    # --- Validação de entrada: falha antes de gastar uma chamada ao LLM -------------------------
    _check_input(ctx, ticket, version)
    # Monta mensagens e hash num único snapshot (evita leitura dupla/TOCTOU), parâmetros e chave de cache.
    messages, prompt_sha256 = ctx.prompts.build_with_hash(version, content_type, profile, ticket.text)
    schema = OUTPUT_SCHEMAS[content_type]
    params = LLMParams(
        model=config.model,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        structured_mode=config.structured_mode,
        reasoning=config.reasoning,
    )
    cache_key = _cache_key(config, content_type, profile, ticket, version, prompt_sha256)
    started = time.perf_counter()
    run_id = uuid.uuid4().hex[:RUN_ID_LENGTH]

    def make_record(**variable: object) -> RunRecord:
        """Registro com os campos comuns a acerto, sucesso e erro; ``variable`` traz o que muda em cada caso."""
        return RunRecord.model_validate(dict(
            run_id=run_id,
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
        ))

    with ctx.inflight.acquire(cache_key):
        # --- Cache: acerto grava uma nova execução (evidência do reaproveitamento) e não chama o LLM ---
        source = _find_cached_source(ctx, cache_key) if use_cache else None
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
            _emit_generation(ctx, record, saved_path, use_cache=use_cache, batch_id=batch_id)
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

        # Chama o LLM com reparo, gera renderização ASCII (se houver) e captura falhas.
        started = time.perf_counter()  # a latência de uma geração real não inclui a consulta ao cache
        try:
            validated = _call_with_repair(ctx, version, messages, schema, params, tally, channel_check)
            output = validated.model_dump(mode="json")
            renderer = _RENDERERS.get(content_type)
            rendered = renderer(validated) if renderer else None
        except DomainError as exc:
            error, raised = RunError(type=type(exc).__name__, message=str(exc)), exc
        latency_ms = int((time.perf_counter() - started) * 1000)

        # Monta o registro final (sucesso ou erro) e persiste no histórico em disco.
        record = make_record(
            status="error" if error else "ok",
            model_used=tally.model_used,
            attempts=max(tally.attempts, 1),
            latency_ms=latency_ms,
            usage=tally.usage,
            llm_calls=tally.calls,
            output=output,
            rendered=rendered,
            error=error,
        )
        saved_path = ctx.runs.save(record)
        # O ponteiro do cache só nasce depois de a execução estar gravada (nunca aponta para o vazio) e só para
        # sucesso: erros nunca entram no cache (ADR 0018). Grava sempre, com ``use_cache`` ligado ou não (ADR 0035).
        if record.status == "ok":
            ctx.cache.put(CacheEntry(cache_key=cache_key, source_run_id=record.run_id, created_at=record.timestamp))
        # Nível INFO sem o texto do ticket (ADR 0019).
        logger.info(
            "execução %s: tipo=%s versão=%s status=%s modelo=%s latência=%dms tentativas=%d",
            record.run_id, content_type.value, version, record.status, record.model_used, latency_ms, record.attempts,
        )
        _emit_generation(ctx, record, saved_path, use_cache=use_cache, batch_id=batch_id)
        return GenerationResult(record=record, saved_path=saved_path, exception=raised)


def _emit_generation(
    ctx: GenerationContext, record: RunRecord, saved_path: str, *, use_cache: bool, batch_id: str | None
) -> None:
    """Emite o evento ``generation`` de uma execução gravada (ADR 0043).

    Leva tudo o que explica o resultado, menos o texto do ticket e a saída (ADR 0019): ambos estão no JSON da
    execução, em ``saved_path``, e o ``run_id`` liga o log a ele.
    """
    ctx.events.emit(EVENT_GENERATION, {
        "run_id": record.run_id,
        "batch_id": batch_id,
        "status": record.status,
        "content_type": record.content_type.value,
        "prompt_version": record.prompt_version,
        "prompt_sha256": record.prompt_sha256,
        "customer": record.customer_profile.model_dump(mode="json"),
        "ticket": {"id": record.ticket.id, "title": record.ticket.title, "chars": len(record.ticket.text)},
        "provider": record.provider,
        "model": record.model,
        "model_used": record.model_used,
        "params": record.params.model_dump(mode="json"),
        "use_cache": use_cache,
        "cache_key": record.cache_key,
        "cache_hit": record.cache_hit,
        "source_run_id": record.source_run_id,
        "attempts": record.attempts,
        "latency_ms": record.latency_ms,
        "usage": record.usage,
        "llm_calls": [call.model_dump(mode="json") for call in record.llm_calls],
        "error": record.error.model_dump(mode="json") if record.error else None,
        "saved_path": saved_path,
    })


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
    """Gera as perguntas de esclarecimento priorizadas (2 a 4), com motivo e o que cada resposta destrava."""
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


def resolve_scenario(ctx: GenerationContext, profile_id: str, ticket_id: str) -> tuple[CustomerProfile, RunTicket]:
    """Resolve perfil e ticket do catálogo (``NotFound`` se algum não existir).

    O ticket é sempre um do catálogo, como no site: um relato novo é cadastrado antes (ADR 0037 e 0040).
    """
    profile = ctx.profiles.get(profile_id)
    catalog_ticket = ctx.tickets.get(ticket_id)
    return profile, RunTicket(id=catalog_ticket.id, title=catalog_ticket.title, text=catalog_ticket.text)


def check_cache_replacement(
    ctx: GenerationContext,
    *,
    profile: CustomerProfile,
    ticket: RunTicket,
    targets: Sequence[tuple[ContentType, str | None]],
    use_cache: bool,
    confirm_replace: bool,
) -> None:
    """Levanta ``CacheReplaceRequired`` se gerar sem consultar o cache trocaria entradas e o pedido não confirmou.

    Só há substituição com ``use_cache`` desligado: ligado, um acerto não grava e um erro não tem entrada para
    trocar. Uma entrada conta quando ainda é utilizável (origem existente, com sucesso e com saída): ponteiro órfão ou
    apontando para erro não perde nada. Examina **todos** os ``targets`` (tipo e versão) antes de qualquer geração e
    junta os conflitos num erro só, para o cliente confirmar tudo de uma vez (ADR 0036).
    """
    # Sem substituição possível (cache consultado) ou com confirmação explícita, nada a verificar.
    if use_cache or confirm_replace:
        return
    conflicts: list[CacheConflict] = []
    for content_type, prompt_version in targets:
        version = _resolve_version(ctx, prompt_version)
        _check_input(ctx, ticket, version)  # mesmos erros de entrada que a geração levantaria
        key = _cache_key(ctx.config, content_type, profile, ticket, version, ctx.registry.actual_sha256(version))
        source = _find_cached_source(ctx, key)
        if source is not None:
            conflicts.append(CacheConflict(
                content_type=content_type, prompt_version=version,
                run_id=source.run_id, created_at=source.timestamp,
            ))
    if conflicts:
        raise CacheReplaceRequired(conflicts)


def generate(
    ctx: GenerationContext,
    *,
    content_type: ContentType,
    profile_id: str,
    ticket_id: str,
    prompt_version: str | None = None,
    use_cache: bool = True,
    confirm_replace: bool = False,
) -> GenerationResult:
    """Ponto de entrada único de API e CLI para um tipo: resolve perfil e ticket e chama o gerador do tipo.

    ``use_cache=False`` não consulta o cache nesta chamada (gera de novo); o resultado é gravado no cache mesmo assim.
    Se isso substituir uma entrada existente, exige ``confirm_replace=True`` (senão ``CacheReplaceRequired``, ADR 0036).
    """
    profile, ticket = resolve_scenario(ctx, profile_id, ticket_id)
    check_cache_replacement(
        ctx, profile=profile, ticket=ticket, targets=[(content_type, prompt_version)],
        use_cache=use_cache, confirm_replace=confirm_replace,
    )
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


# Aviso do modo ``all`` quando só parte dos tipos falha (o site mostra num toast; a CLI imprime em stderr).
PARTIAL_FAILURE_MESSAGE = "Houve erro em: {types}."


@dataclass(frozen=True)
class BatchResult:
    """Resultado do modo ``all``: um item por tipo, na ordem de ``ContentType``."""

    items: list[BatchItem]

    @property
    def errors(self) -> list[DomainError]:
        """Exceções dos tipos que falharam, na ordem dos itens."""
        return [item.error for item in self.items if item.error is not None]

    @property
    def warning(self) -> str | None:
        """Aviso de falha parcial: os tipos que falharam, quando ao menos um deu certo (``None`` se não houve falha).

        A frase é a mesma no site (toast) e na CLI; se **todos** falharem, não há aviso: ``raise_if_all_failed``
        levanta o erro do primeiro.
        """
        failed = [item.content_type.label for item in self.items if not item.ok]
        if not failed or len(failed) == len(self.items):
            return None
        return PARTIAL_FAILURE_MESSAGE.format(types=", ".join(failed))

    def raise_if_all_failed(self) -> None:
        """Levanta o erro do primeiro tipo se nenhum deu certo: nada foi gerado, então o pedido inteiro falhou."""
        if self.errors and len(self.errors) == len(self.items):
            raise self.errors[0]

    def to_payload(self) -> "BatchSummary":
        """Converte o lote para a estrutura serializável compartilhada por API e CLI."""
        results = []
        for item in self.items:
            if item.ok and item.result is not None:
                results.append(BatchItemSummary(
                    content_type=item.content_type, saved_path=item.result.saved_path, run=item.result.record
                ))
                continue
            error = RunError(type=type(item.error).__name__, message=str(item.error))
            results.append(BatchItemSummary(
                content_type=item.content_type,
                saved_path=item.result.saved_path if item.result else None,
                run=item.result.record if item.result else None,
                error=error,
            ))
        return BatchSummary(results=results, warning=self.warning)


class BatchItemSummary(BaseModel):
    """Um tipo no modo ``all``: com sucesso traz ``run``; com falha, ``error``."""

    content_type: ContentType
    saved_path: str | None = None
    run: RunRecord | None = None
    error: RunError | None = None


class BatchSummary(BaseModel):
    """Resultado consolidado do modo ``all`` (compartilhado por API e CLI)."""

    results: list[BatchItemSummary]
    warning: str | None = None


def generate_all(
    ctx: GenerationContext,
    *,
    profile_id: str,
    ticket_id: str,
    prompt_version: str | None = None,
    use_cache: bool = True,
    confirm_replace: bool = False,
) -> BatchResult:
    """Gera os quatro tipos em paralelo (ADR 0007 e 0015) e devolve um item por tipo.

    Cada tipo consulta o cache de forma independente (a chave inclui o tipo): um pode acertar e outro gerar.

    Erros de entrada (perfil, ticket ou versão inválidos) levantam **uma vez**, antes de abrir as threads. Depois
    disso, cada tipo é independente: falhas do LLM ou do schema de um tipo viram um item com erro e os outros
    seguem. Cada tipo grava o próprio arquivo de execução (nomes únicos por ``run_id``, sem corrida).
    Com ``use_cache`` desligado, substituir entradas do cache exige ``confirm_replace=True`` (ADR 0036).
    """
    # Resolve perfil e ticket e executa uma única vez antes de abrir threads.
    profile, ticket = resolve_scenario(ctx, profile_id, ticket_id)
    _check_input(ctx, ticket, _resolve_version(ctx, prompt_version))
    # Antes de abrir as threads: os conflitos dos quatro tipos saem juntos, e nada é gerado sem a confirmação.
    check_cache_replacement(
        ctx, profile=profile, ticket=ticket, targets=[(content_type, prompt_version) for content_type in _GENERATORS],
        use_cache=use_cache, confirm_replace=confirm_replace,
    )

    batch_id = uuid.uuid4().hex[:RUN_ID_LENGTH]

    def run_one(content_type: ContentType) -> BatchItem:
        """Executa um tipo isolando as falhas esperadas do domínio no próprio item."""
        try:
            result = _generate_result(ctx, content_type, profile, ticket, prompt_version, use_cache, batch_id)
        except DomainError as exc:  # ex.: NotFound do arquivo de prompt do tipo
            return BatchItem(content_type, None, exc)
        return BatchItem(content_type, result, result.exception)

    # Dispara os quatro tipos em paralelo e devolve os resultados na ordem fixa.
    types = list(_GENERATORS)
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=len(types), thread_name_prefix="gen") as pool:
        items = list(pool.map(run_one, types))  # map preserva a ordem de ``types``
    batch = BatchResult(items=items)
    _emit_batch(ctx, batch, batch_id=batch_id, profile=profile, ticket=ticket, prompt_version=prompt_version,
                use_cache=use_cache, latency_ms=int((time.perf_counter() - started) * 1000))
    return batch


def _emit_batch(
    ctx: GenerationContext,
    batch: BatchResult,
    *,
    batch_id: str,
    profile: CustomerProfile,
    ticket: RunTicket,
    prompt_version: str | None,
    use_cache: bool,
    latency_ms: int,
) -> None:
    """Emite o evento ``generation_batch`` do modo ``all``: o desfecho de cada tipo e o total gasto (ADR 0043)."""
    usage: dict[str, int] = {}
    results = []
    for item in batch.items:
        record = item.result.record if item.result else None
        for key, value in (record.usage if record else {}).items():
            usage[key] = usage.get(key, 0) + value
        results.append({
            "content_type": item.content_type.value,
            "status": "ok" if item.ok else "error",
            "run_id": record.run_id if record else None,
            "cache_hit": record.cache_hit if record else False,
            "error": {"type": type(item.error).__name__, "message": str(item.error)} if item.error else None,
        })
    ctx.events.emit(EVENT_GENERATION_BATCH, {
        "batch_id": batch_id,
        "customer_id": profile.id,
        "ticket_id": ticket.id,
        "prompt_version": _resolve_version(ctx, prompt_version),
        "use_cache": use_cache,
        "latency_ms": latency_ms,
        "ok": sum(1 for item in batch.items if item.ok),
        "failed": [item.content_type.value for item in batch.items if not item.ok],
        "usage": usage,
        "results": results,
    })
