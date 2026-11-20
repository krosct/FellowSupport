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


class LLMPorSchema:
    """LLM de teste seguro para threads: a resposta depende do schema pedido (não da ordem das chamadas).

    ``respostas`` mapeia o schema para um texto ou uma exceção; schema ausente cai no ``FakeLLM``. Útil no modo
    ``all``, em que as quatro chamadas chegam em ordem imprevisível.
    """

    def __init__(self, respostas: dict[type[BaseModel], str | Exception]) -> None:
        import threading

        from app.adapters.llm.fake import FakeLLM

        self._respostas = respostas
        self._fake = FakeLLM()
        self._lock = threading.Lock()
        self.chamadas: list[type[BaseModel]] = []
        self.threads: set[int] = set()

    def complete(self, messages: Sequence[ChatMessage], schema: type[BaseModel], params: LLMParams) -> LLMResult:
        import threading

        with self._lock:
            self.chamadas.append(schema)
            self.threads.add(threading.get_ident())
        item = self._respostas.get(schema)
        if item is None:
            return self._fake.complete(messages, schema, params)
        if isinstance(item, Exception):
            raise item
        usage = {"prompt_tokens": 1, "completion_tokens": 1}
        return LLMResult(text=item, parsed=extract_json_object(item), usage=usage, latency_ms=1,
                         model_used="vendor/efetivo")
