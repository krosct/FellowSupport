"""Fábrica do cliente de LLM conforme o ``Settings`` (ADR 0023). Chamada só pela raiz de composição."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel

from app.adapters.llm.fake import FakeLLM
from app.adapters.llm.openai_compat import OpenAICompatClient
from app.config import Settings
from app.domain.errors import LLMUnavailable
from app.ports.llm import ChatMessage, LLMClient, LLMParams, LLMResult

MISSING_KEY_MESSAGE = (
    "LLM_PROVIDER=openrouter exige OPENROUTER_API_KEY no .env. Preencha a chave ou use LLM_PROVIDER=fake."
)


class MissingKeyLLM:
    """Cliente que falha com mensagem clara ao ser usado sem chave.

    A falha acontece no uso, não na criação, para a API e a CLI subirem (catálogo, metadados e versões seguem
    funcionando) e o erro aparecer no toast e na CLI como ``LLMUnavailable``.
    """

    def complete(self, messages: Sequence[ChatMessage], schema: type[BaseModel], params: LLMParams) -> LLMResult:
        raise LLMUnavailable(MISSING_KEY_MESSAGE)


def build_llm_client(settings: Settings) -> LLMClient:
    """Cria ``FakeLLM`` ou ``OpenAICompatClient`` conforme ``LLM_PROVIDER``."""
    if settings.llm_provider == "fake":
        return FakeLLM()
    api_key = settings.openrouter_api_key.get_secret_value()
    if not api_key:
        return MissingKeyLLM()
    return OpenAICompatClient(
        api_key=api_key,
        base_url=settings.llm_base_url,
        timeout_s=settings.llm_timeout_s,
        max_retries=settings.llm_max_retries,
    )
