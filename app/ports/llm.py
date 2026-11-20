"""Porta de LLM (ADR 0002, 0003 e 0004): o contrato que o núcleo exige de qualquer provedor de linguagem.

O núcleo conhece só estes tipos. Quem fala com o SDK, com a rede ou com um simulador são os adaptadores em
``adapters/llm``. As portas são síncronas (ADR 0015).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol, TypedDict

from pydantic import BaseModel

# Estratégias de saída estruturada (ADR 0004), definidas uma única vez e reutilizadas pela configuração.
#   json_schema: o provedor impõe o JSON Schema · json_object: o provedor impõe "algum JSON" e o schema vai
#   no prompt · prompt: só instrução em texto, para modelos sem suporte a ``response_format``.
StructuredMode = Literal["json_schema", "json_object", "prompt"]


class ChatMessage(TypedDict):
    """Uma mensagem no formato de chat usado por todos os provedores compatíveis."""

    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class LLMParams:
    """Parâmetros de uma chamada. Entram no registro da execução e, na Etapa 3, na chave de cache."""

    model: str
    temperature: float
    max_tokens: int
    structured_mode: StructuredMode


@dataclass(frozen=True)
class LLMResult:
    """Resposta de uma chamada: o texto bruto e o que o adaptador conseguiu extrair e medir.

    ``parsed`` é o objeto JSON decodificado do texto (ou ``None`` se não houver JSON utilizável). Quem decide se
    ele é válido para o schema é o serviço, com Pydantic.
    """

    text: str
    parsed: dict | None
    usage: dict[str, int] = field(default_factory=dict)
    latency_ms: int = 0
    model_used: str = ""


class LLMClient(Protocol):
    """Gera uma resposta estruturada a partir de mensagens de chat."""

    def complete(self, messages: Sequence[ChatMessage], schema: type[BaseModel], params: LLMParams) -> LLMResult:
        """Chama o modelo.

        Levanta ``LLMUnavailable`` (provedor fora do ar, sem chave, erro de rede) ou ``LLMRateLimited`` (429).
        Uma resposta que não valida contra ``schema`` NÃO é erro aqui: devolve-se o texto e o serviço decide.
        Exceção: resposta cortada pelo limite de tokens e sem JSON aproveitável levanta ``InvalidLLMOutput``
        direto, porque o reparo bateria no mesmo limite.
        """
        ...
