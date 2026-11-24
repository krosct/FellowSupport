"""Porta de LLM (ADR 0002, 0003 e 0004): o contrato que o núcleo exige de qualquer provedor de linguagem.

O núcleo conhece só estes tipos. Quem fala com o SDK, com a rede ou com um simulador são os adaptadores em
``adapters/llm``. As portas são síncronas (ADR 0015).
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol, TypedDict

from pydantic import BaseModel

# Estratégias de saída estruturada (ADR 0004), definidas uma única vez e reutilizadas pela configuração.
#   json_schema: o provedor impõe o JSON Schema · json_object: o provedor impõe "algum JSON" e o schema vai
#   no prompt · prompt: só instrução em texto, para modelos sem suporte a ``response_format``.
StructuredMode = Literal["json_schema", "json_object", "prompt"]


# Controle do raciocínio dos modelos que "pensam" antes de responder (ADR 0027). ``default`` não envia o
# parâmetro (o modelo faz o que faz por padrão); ``off`` pede o raciocínio desligado; os demais pedem esforço.
ReasoningMode = Literal["default", "off", "none", "low", "medium", "high"]


# Estruturas de entrada e saída trocadas com qualquer provedor de LLM.
class ChatMessage(TypedDict):
    """Uma mensagem no formato de chat usado por todos os provedores compatíveis."""

    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class LLMParams:
    """Parâmetros de uma chamada. Entram no registro da execução e na chave de cache."""

    model: str
    temperature: float
    max_tokens: int
    structured_mode: StructuredMode
    reasoning: ReasoningMode = "default"


@dataclass(frozen=True)
class LLMResult:
    """Resposta de uma chamada: o texto bruto e o que o adaptador conseguiu extrair e medir.

    ``parsed`` é o objeto JSON decodificado do texto (ou ``None`` se não houver JSON utilizável). Quem decide se
    ele é válido para o schema é o serviço, com Pydantic.

    ``finish_reason`` diz por que o modelo parou (``stop``, ``length``...): com ``length`` e sem JSON, o serviço
    falha já, com o gasto registrado. ``provider_used`` e ``response_id`` identificam quem atendeu de fato (o
    OpenRouter roteia o mesmo modelo entre vários provedores) e a geração no provedor; vazios quando não informados.
    """

    text: str
    parsed: dict | None
    usage: dict[str, int] = field(default_factory=dict)
    latency_ms: int = 0
    model_used: str = ""
    finish_reason: str = ""
    provider_used: str = ""
    response_id: str = ""


class LLMClient(Protocol):
    """Gera uma resposta estruturada a partir de mensagens de chat."""

    def complete(self, messages: Sequence[ChatMessage], schema: type[BaseModel], params: LLMParams) -> LLMResult:
        """Chama o modelo.

        Levanta ``LLMUnavailable`` (provedor fora do ar, sem chave, erro de rede) ou ``LLMRateLimited`` (429).
        Uma resposta que não valida contra ``schema`` NÃO é erro aqui: devolve-se o texto e o serviço decide.
        Isso vale também para a resposta cortada pelo limite de tokens: o adaptador devolve ``finish_reason`` e o
        uso medido, e o serviço decide (assim o gasto e o provedor entram no registro da execução, ADR 0042).
        """
        ...
