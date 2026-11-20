"""Raiz de composição (ADR 0002): único lugar que liga portas a adaptadores concretos.

API e CLI pedem um ``Container`` pronto e nunca instanciam repositórios nem clientes por conta própria. A
Etapa 3 acrescenta aqui o cache.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.adapters.llm.factory import build_llm_client
from app.adapters.storage.json_files import JsonProfileRepo, JsonRunRepo, JsonTicketRepo
from app.adapters.storage.prompt_files import FilePromptStore
from app.config import Settings, get_settings
from app.domain.prompting.engine import PromptBuilder
from app.domain.prompting.registry import PromptRegistry
from app.ports.llm import LLMClient
from app.ports.repositories import ProfileRepo, TicketRepo
from app.services.generators import GenerationConfig, GenerationContext


@dataclass(frozen=True)
class Container:
    """Dependências já ligadas, entregues às camadas de entrada."""

    settings: Settings
    profiles: ProfileRepo
    tickets: TicketRepo
    prompts: PromptRegistry
    generation: GenerationContext


def build_container(settings: Settings | None = None, *, llm: LLMClient | None = None) -> Container:
    """Monta o ``Container`` a partir do ``Settings`` (ou do padrão do processo).

    ``llm`` permite injetar outro cliente (os testes usam um que falha ou devolve saídas roteirizadas); sem ele,
    a fábrica escolhe ``fake`` ou ``openrouter`` conforme ``LLM_PROVIDER``.
    """
    settings = settings or get_settings()
    profiles = JsonProfileRepo(settings.catalog_dir)
    tickets = JsonTicketRepo(settings.catalog_dir)
    registry = PromptRegistry(FilePromptStore(settings.prompts_dir))
    generation = GenerationContext(
        llm=llm or build_llm_client(settings),
        prompts=PromptBuilder(registry),
        registry=registry,
        runs=JsonRunRepo(settings.data_dir),
        profiles=profiles,
        tickets=tickets,
        config=GenerationConfig(
            provider=settings.llm_provider,
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            structured_mode=settings.llm_structured_mode,
            reasoning=settings.llm_reasoning,
            default_prompt_version=settings.default_prompt_version,
            max_ticket_chars=settings.max_ticket_chars,
            save_prompt_messages=settings.save_prompt_messages,
            timezone=settings.app_timezone,
        ),
    )
    return Container(settings=settings, profiles=profiles, tickets=tickets, prompts=registry, generation=generation)
