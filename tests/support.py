"""Apoio compartilhado pelos testes: um cliente de LLM roteirizado que implementa a porta ``LLMClient``."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel

from app.domain.llm_output import extract_json_object
from app.ports.llm import ChatMessage, LLMParams, LLMResult


class LLMRoteirizado:
    """LLM de teste: devolve (ou levanta) as respostas na ordem e guarda as mensagens recebidas."""

    def __init__(self, *respostas: str | Exception) -> None:
        self._respostas = list(respostas)
        self.chamadas: list[list[ChatMessage]] = []

    def complete(self, messages: Sequence[ChatMessage], schema: type[BaseModel], params: LLMParams) -> LLMResult:
        self.chamadas.append([dict(m) for m in messages])  # type: ignore[misc]
        item = self._respostas.pop(0)
        if isinstance(item, Exception):
            raise item
        return LLMResult(
            text=item, parsed=extract_json_object(item), usage={"prompt_tokens": 10, "completion_tokens": 5},
            latency_ms=1, model_used="vendor/efetivo",
        )
