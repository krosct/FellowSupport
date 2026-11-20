"""Casos de uso de geração de conteúdo (ADR 0007): o núcleo ``_generate`` e uma função pública por tipo.

Fluxo de ``_generate``: monta as mensagens com o motor de prompts, chama o LLM, valida a saída com o schema
Pydantic do tipo, faz **uma** tentativa de reparo se a validação falhar (ADR 0004) e persiste a execução em um
arquivo JSON (ADR 0009), inclusive quando dá erro (``status: "error"``, nunca reaproveitado pelo cache).

Este módulo não conhece FastAPI, SDK nem disco: só portas e domínio. Quem liga os adaptadores é o ``container``.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ValidationError

from app.domain.errors import DomainError, InvalidLLMOutput, ValidationFailed
from app.domain.llm_output import format_validation_error
from app.domain.models import (
    FREE_TICKET_TITLE,
    OUTPUT_SCHEMAS,
    ContentType,
    CustomerProfile,
    RunError,
    RunParams,
    RunRecord,
    RunTicket,
)
from app.domain.prompting.engine import PromptBuilder
from app.domain.prompting.registry import PromptRegistry
from app.ports.llm import ChatMessage, LLMClient, LLMParams, LLMResult, StructuredMode
from app.ports.repositories import ProfileRepo, RunRepo, TicketRepo

logger = logging.getLogger("fellowsupport.generators")

# Tamanho do identificador curto de execução (parte do nome do arquivo salvo).
RUN_ID_LENGTH = 12

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
    default_prompt_version: str
    max_ticket_chars: int
    save_prompt_messages: bool
    timezone: str


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
    profiles: ProfileRepo
    tickets: TicketRepo
    config: GenerationConfig
    clock: Callable[[ZoneInfo], datetime] = field(default=_system_clock)


@dataclass(frozen=True)
class GenerationResult:
    """Resultado de uma geração: o registro completo e o caminho do JSON salvo."""

    record: RunRecord
    saved_path: str


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


def _validate(schema: type[BaseModel], result: LLMResult) -> tuple[BaseModel | None, str]:
    """Valida a resposta contra o schema. Devolve ``(saída, "")`` ou ``(None, descrição do problema)``."""
    if result.parsed is None:
        return None, "A resposta não contém um objeto JSON válido."
    try:
        return schema.model_validate(result.parsed), ""
    except ValidationError as exc:
        return None, format_validation_error(exc)


def _call_with_repair(
    ctx: GenerationContext,
    version: str,
    messages: list[ChatMessage],
    schema: type[BaseModel],
    params: LLMParams,
    tally: _Tally,
) -> BaseModel:
    """Chama o LLM e valida; se a saída for inválida, faz uma única tentativa de reparo (ADR 0004).

    Levanta ``InvalidLLMOutput`` se a saída continuar inválida; erros do provedor (``LLMUnavailable`` e
    ``LLMRateLimited``) sobem como estão.
    """
    result = ctx.llm.complete(messages, schema, params)
    tally.add(result)
    output, problem = _validate(schema, result)
    if output is not None:
        return output

    logger.warning("Saída inválida na 1ª tentativa; tentando reparo (%s)", problem.splitlines()[0])
    repair_messages = ctx.prompts.build_repair(version, messages, result.text, problem)
    result = ctx.llm.complete(repair_messages, schema, params)
    tally.add(result)
    output, problem = _validate(schema, result)
    if output is None:
        raise InvalidLLMOutput(f"O modelo não devolveu uma saída válida, mesmo após o reparo:\n{problem}")
    return output


def _generate(
    ctx: GenerationContext,
    content_type: ContentType,
    profile: CustomerProfile,
    ticket: RunTicket,
    prompt_version: str | None,
) -> GenerationResult:
    """Núcleo comum aos geradores: monta, chama, valida, repara se preciso e persiste a execução.

    Erros de entrada (ticket grande demais, versão inexistente) levantam antes de qualquer chamada e **não**
    geram registro. Erros do LLM e saída inválida geram um registro ``status: "error"`` e sobem para o chamador.
    """
    config = ctx.config
    version = prompt_version or config.default_prompt_version

    # --- Validação de entrada: falha antes de gastar uma chamada ao LLM -------------------------
    if not ticket.text.strip():
        raise ValidationFailed("O texto do ticket está vazio.")
    if len(ticket.text) > config.max_ticket_chars:
        raise ValidationFailed(
            f"O texto do ticket tem {len(ticket.text)} caracteres; o limite é {config.max_ticket_chars}."
        )
    ctx.registry.get(version)  # NotFound se a versão não existir
    messages = ctx.prompts.build(version, content_type, profile, ticket.text)
    schema = OUTPUT_SCHEMAS[content_type]
    params = LLMParams(
        model=config.model,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        structured_mode=config.structured_mode,
    )
    prompt_sha256 = ctx.registry.actual_sha256(version)

    # Etapa 3 (cache): calcular a chave a partir de perfil, ticket, tipo, versão, hash do prompt e params;
    # em caso de acerto, gravar a execução com cache_hit=True e devolver sem chamar o LLM.

    # --- Chamada ao LLM (com reparo) e registro ------------------------------------------------
    tally = _Tally()
    error: RunError | None = None
    raised: DomainError | None = None
    output: dict | None = None
    started = time.perf_counter()
    try:
        output = _call_with_repair(ctx, version, messages, schema, params, tally).model_dump(mode="json")
    except DomainError as exc:
        error, raised = RunError(type=type(exc).__name__, message=str(exc)), exc
    latency_ms = int((time.perf_counter() - started) * 1000)

    record = RunRecord(
        run_id=uuid.uuid4().hex[:RUN_ID_LENGTH],
        timestamp=ctx.clock(ZoneInfo(config.timezone)).isoformat(timespec="seconds"),
        status="error" if error else "ok",
        customer_id=profile.id,
        customer_profile=profile,
        ticket=ticket,
        content_type=content_type,
        prompt_version=version,
        prompt_sha256=prompt_sha256,
        provider=config.provider,
        model=config.model,
        model_used=tally.model_used,
        params=RunParams(
            temperature=config.temperature, max_tokens=config.max_tokens, structured_mode=config.structured_mode
        ),
        attempts=max(tally.attempts, 1),
        latency_ms=latency_ms,
        usage=tally.usage,
        prompt_messages=[dict(m) for m in messages] if config.save_prompt_messages else [],
        output=output,
        error=error,
    )
    saved_path = ctx.runs.save(record)
    # Nível INFO sem o texto do ticket (ADR 0019).
    logger.info(
        "execução %s: tipo=%s versão=%s status=%s modelo=%s latência=%dms tentativas=%d",
        record.run_id, content_type.value, version, record.status, record.model_used, latency_ms, record.attempts,
    )
    if raised is not None:
        raise raised
    return GenerationResult(record=record, saved_path=saved_path)


def generate_diagnosis(
    ctx: GenerationContext, profile: CustomerProfile, ticket: RunTicket, prompt_version: str | None = None
) -> GenerationResult:
    """Gera o diagnóstico (hipóteses, evidências, faltantes e conclusão) do ticket para o perfil."""
    return _generate(ctx, ContentType.DIAGNOSIS, profile, ticket, prompt_version)


# Tipo de conteúdo -> gerador disponível. A Etapa 2 registra aqui os outros três.
_GENERATORS: dict[ContentType, Callable[..., GenerationResult]] = {
    ContentType.DIAGNOSIS: generate_diagnosis,
}


def generate(
    ctx: GenerationContext,
    *,
    content_type: ContentType,
    profile_id: str,
    ticket_id: str | None = None,
    ticket_text: str | None = None,
    prompt_version: str | None = None,
) -> GenerationResult:
    """Ponto de entrada único de API e CLI: resolve perfil e ticket e chama o gerador do tipo.

    O ticket vem do catálogo (``ticket_id``) **ou** de texto livre (``ticket_text``); exatamente um dos dois.
    """
    if (ticket_id is None) == (ticket_text is None):
        raise ValidationFailed("Informe o ticket do catálogo (ticket_id) ou um texto livre (ticket_text), só um.")
    generator = _GENERATORS.get(content_type)
    if generator is None:
        raise ValidationFailed(f"A geração de «{content_type.label}» ainda não está disponível.")

    profile = ctx.profiles.get(profile_id)
    if ticket_id is not None:
        catalog_ticket = ctx.tickets.get(ticket_id)
        ticket = RunTicket(id=catalog_ticket.id, title=catalog_ticket.title, text=catalog_ticket.text)
    else:
        ticket = RunTicket(id=None, title=FREE_TICKET_TITLE, text=(ticket_text or "").strip())
    return generator(ctx, profile, ticket, prompt_version)
