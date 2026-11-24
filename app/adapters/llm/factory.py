"""Fábrica do cliente de LLM conforme o ``Settings`` (ADR 0023). Chamada só pela raiz de composição."""

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
SESSION_KEY_MESSAGE = (
    "Informe sua openrouter_api_key nas configurações de chaves da sessão (botão Provedor/Modelo no topo)."
)


class MissingKeyLLM:
    """Cliente que falha com mensagem clara ao ser usado sem chave.

    A falha acontece no uso, não na criação, para a API e a CLI subirem (catálogo, metadados e versões seguem
    funcionando) e o erro aparecer no toast e na CLI como ``LLMUnavailable``.
    """

    def __init__(self, message: str = MISSING_KEY_MESSAGE) -> None:
        self._message = message

    def complete(self, messages: Sequence[ChatMessage], schema: type[BaseModel], params: LLMParams) -> LLMResult:
        """Sempre falha: sem chave não há como chamar o provedor."""
        raise LLMUnavailable(self._message)


def build_llm_client(settings: Settings, *, api_key_override: str | None = None) -> LLMClient:
    """Cria ``FakeLLM`` ou ``OpenAICompatClient`` conforme ``LLM_PROVIDER``.

    Em deploy (``PUBLIC_URL`` definida), a chave do servidor não é usada automaticamente: o usuário deve informar
    sua própria chave na sessão (``api_key_override``).
    """
    if settings.llm_provider == "fake":
        return FakeLLM()
    if api_key_override is not None:
        api_key = api_key_override.strip()
        if not api_key:
            return MissingKeyLLM(SESSION_KEY_MESSAGE if settings.public_url else MISSING_KEY_MESSAGE)
    elif settings.public_url:
        return MissingKeyLLM(SESSION_KEY_MESSAGE)
    else:
        api_key = settings.openrouter_api_key.get_secret_value()
        if not api_key:
            return MissingKeyLLM(MISSING_KEY_MESSAGE)
    return OpenAICompatClient(
        api_key=api_key,
        base_url=settings.llm_base_url,
        timeout_s=settings.llm_timeout_s,
        max_retries=settings.llm_max_retries,
    )
