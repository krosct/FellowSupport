"""Adaptador de LLM sobre o SDK ``openai`` (ADR 0003): OpenRouter, DeepSeek, OpenAI ou qualquer endpoint compatível.

Responsabilidades, todas escondidas atrás da porta ``LLMClient``:
- timeout e novas tentativas com backoff (o próprio SDK repete 429 e 5xx até ``max_retries``);
- os três modos de saída estruturada (ADR 0004): ``json_schema``, ``json_object`` e ``prompt``;
- medir latência, uso de tokens e o modelo efetivo (``response.model``), que pode diferir do pedido;
- traduzir os erros do SDK para as exceções do domínio (ADR 0018), sem expor chave nem cabeçalhos.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Sequence
from typing import Any

import openai
from pydantic import BaseModel

from app.domain.errors import RATE_LIMIT_MESSAGE, InvalidLLMOutput, LLMRateLimited, LLMUnavailable
from app.domain.llm_output import extract_json_object
from app.ports.llm import ChatMessage, LLMParams, LLMResult, ReasoningMode, StructuredMode

logger = logging.getLogger("fellowsupport.llm")

# Tamanho máximo da mensagem de erro do provedor repassada ao usuário (evita despejar HTML ou corpos enormes).
_MAX_ERROR_CHARS = 300

# Instrução anexada ao prompt de sistema quando o provedor não impõe o schema (modos json_object e prompt).
_SCHEMA_INSTRUCTION = (
    "Responda somente com um objeto JSON válido, sem texto antes ou depois e sem cercas de código, que siga "
    "exatamente este JSON Schema:\n{schema}"
)


# Corpo do parâmetro ``reasoning`` do OpenRouter para cada modo (``default`` não envia nada). ``off`` usa
# ``enabled: false``; ``none`` usa ``effort: none``. Modelos de raciocínio obrigatório podem ignorar ou recusar.
REASONING_REQUESTS: dict[str, dict[str, Any]] = {
    "off": {"enabled": False},
    "none": {"effort": "none"},
    "low": {"effort": "low"},
    "medium": {"effort": "medium"},
    "high": {"effort": "high"},
}


def _reasoning_body(mode: ReasoningMode) -> dict[str, Any] | None:
    """``extra_body`` com o controle de raciocínio do modo, ou ``None`` no modo ``default``."""
    request = REASONING_REQUESTS.get(mode)
    return {"reasoning": request} if request else None


def _response_format(schema: type[BaseModel], mode: StructuredMode) -> dict[str, Any] | None:
    """Valor de ``response_format`` para o modo pedido; ``None`` no modo ``prompt`` (sem imposição do provedor)."""
    if mode == "json_schema":
        return {
            "type": "json_schema",
            "json_schema": {"name": schema.__name__, "strict": True, "schema": schema.model_json_schema()},
        }
    if mode == "json_object":
        return {"type": "json_object"}
    return None


def _with_schema_instruction(
    messages: Sequence[ChatMessage], schema: type[BaseModel], mode: StructuredMode
) -> list[ChatMessage]:
    """Copia as mensagens e, nos modos sem imposição de schema, anexa o JSON Schema ao prompt de sistema.

    Anexar à primeira mensagem de sistema (em vez de criar outra no fim) evita erro em modelos que aceitam
    ``system`` só na primeira posição.
    """
    copied: list[ChatMessage] = [{"role": m["role"], "content": m["content"]} for m in messages]
    if mode == "json_schema":
        return copied
    instruction = _SCHEMA_INSTRUCTION.format(schema=json.dumps(schema.model_json_schema(), ensure_ascii=False))
    if copied and copied[0]["role"] == "system":
        copied[0]["content"] = f"{copied[0]['content']}\n\n{instruction}"
    else:
        copied.insert(0, {"role": "system", "content": instruction})
    return copied


def _short(message: str) -> str:
    """Normaliza espaços e limita o tamanho da mensagem de erro do provedor."""
    message = " ".join(str(message).split())
    return message if len(message) <= _MAX_ERROR_CHARS else message[:_MAX_ERROR_CHARS] + "..."


class OpenAICompatClient:
    """``LLMClient`` real, para qualquer endpoint compatível com a API de chat da OpenAI."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        timeout_s: float,
        max_retries: int,
        http_client: Any | None = None,
    ) -> None:
        """Cria o cliente do SDK. ``http_client`` existe para os testes injetarem um transporte simulado."""
        self._client = openai.OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_s,
            max_retries=max_retries,
            http_client=http_client,
        )

    def complete(self, messages: Sequence[ChatMessage], schema: type[BaseModel], params: LLMParams) -> LLMResult:
        """Chama o modelo e devolve texto, JSON extraído, uso, latência e modelo efetivo."""
        request: dict[str, Any] = {
            "model": params.model,
            "messages": _with_schema_instruction(messages, schema, params.structured_mode),
            "temperature": params.temperature,
            "max_tokens": params.max_tokens,
        }
        response_format = _response_format(schema, params.structured_mode)
        if response_format is not None:
            request["response_format"] = response_format
        extra_body = _reasoning_body(params.reasoning)
        if extra_body is not None:
            request["extra_body"] = extra_body  # campo fora do contrato OpenAI: o SDK o mescla ao corpo

        started = time.perf_counter()
        try:
            response = self._client.chat.completions.create(**request)
        except openai.RateLimitError as exc:
            # O texto cru do provedor vai só para o log; quem usa o sistema lê a frase curta e única do domínio.
            logger.warning("provedor respondeu 429: %s", _short(exc.message))
            raise LLMRateLimited(RATE_LIMIT_MESSAGE) from exc
        except openai.APITimeoutError as exc:
            raise LLMUnavailable("O provedor de LLM não respondeu a tempo (timeout).") from exc
        except openai.APIConnectionError as exc:
            raise LLMUnavailable("Não foi possível conectar ao provedor de LLM.") from exc
        except openai.APIStatusError as exc:
            # 401/403 (chave), 404 (modelo), 400 (parâmetro recusado) e 5xx: todos "indisponível" para o usuário.
            raise LLMUnavailable(f"O provedor de LLM respondeu {exc.status_code}: {_short(exc.message)}") from exc
        latency_ms = int((time.perf_counter() - started) * 1000)

        return self._to_result(response, latency_ms)

    @staticmethod
    def _to_result(response: Any, latency_ms: int) -> LLMResult:
        """Converte a resposta do SDK em ``LLMResult`` e trata respostas 200 que trazem erro no corpo."""
        choices = getattr(response, "choices", None)
        if not choices:
            # Alguns provedores (OpenRouter) devolvem 200 com {"error": {...}} quando o modelo falha.
            error = getattr(response, "error", None)
            error = error if isinstance(error, dict) else {}
            detail = _short(error.get("message", "resposta sem conteúdo"))
            if error.get("code") == 429:
                logger.warning("provedor respondeu 429 no corpo: %s", detail)
                raise LLMRateLimited(RATE_LIMIT_MESSAGE)
            raise LLMUnavailable(f"O provedor de LLM não devolveu resposta: {detail}")

        choice = choices[0]
        text = (choice.message.content or "").strip()
        parsed = extract_json_object(text)
        usage = {}
        if response.usage is not None:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens or 0,
                "completion_tokens": response.usage.completion_tokens or 0,
            }
            # Modelos de raciocínio gastam parte de max_tokens "pensando"; registrar isso explica respostas
            # vazias ou cortadas. Só entra quando o provedor informa e é maior que zero.
            details = getattr(response.usage, "completion_tokens_details", None)
            reasoning = getattr(details, "reasoning_tokens", None) or 0
            if reasoning:
                usage["reasoning_tokens"] = reasoning
        if choice.finish_reason == "length" and parsed is None:
            # Cortada pelo limite de tokens e sem JSON aproveitável: o reparo bateria no mesmo limite e gastaria
            # outra chamada, então falha já com a causa e o remédio. Modelos de raciocínio costumam cair aqui.
            thinking = usage.get("reasoning_tokens", 0)
            raise InvalidLLMOutput(
                f"A resposta foi cortada pelo limite de {usage.get('completion_tokens', 0)} tokens "
                f"({thinking} gastos em raciocínio) antes de completar o JSON. Aumente LLM_MAX_TOKENS."
            )
        return LLMResult(
            text=text,
            parsed=parsed,
            usage=usage,
            latency_ms=latency_ms,
            model_used=response.model or "",
        )
