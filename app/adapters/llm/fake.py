"""Provedor de LLM simulado (ADR 0023): responde sem rede, sem chave e sem custo.

Devolve sempre o mesmo JSON, válido pelo schema pedido, para a mesma entrada. Serve para rodar o projeto inteiro
offline, para a demonstração e para os testes. As respostas são marcadas como simuladas: elas provam o fluxo,
não a qualidade de um modelo real.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Sequence

from pydantic import BaseModel

from app.domain.errors import ValidationFailed
from app.domain.models import Conclusion, Confidence, Diagnosis, Hypothesis, MissingInfo
from app.ports.llm import ChatMessage, LLMParams, LLMResult

# Identificador devolvido em ``model_used``: deixa claro, no JSON salvo, que não houve modelo real.
FAKE_MODEL_NAME = "fake-llm"

# Aviso embutido no texto que o cliente leria, para ninguém confundir amostra simulada com real.
SIMULATED_NOTICE = "(Resposta simulada, sem modelo real.)"

# Tamanho máximo do trecho do ticket citado nas evidências.
_SNIPPET_CHARS = 90

_TICKET_TAG = re.compile(r"<ticket>(.*?)</ticket>", re.DOTALL)


def _ticket_snippet(messages: Sequence[ChatMessage]) -> str:
    """Primeiro trecho do texto do ticket (entre ``<ticket>`` e ``</ticket>``), para a resposta parecer ligada
    à entrada. Sem as tags, devolve um texto genérico."""
    for message in reversed(messages):
        found = _TICKET_TAG.search(message["content"])
        if found:
            text = " ".join(found.group(1).split())
            return text[:_SNIPPET_CHARS].rstrip() + ("..." if len(text) > _SNIPPET_CHARS else "")
    return "relato do cliente"


def _diagnosis(snippet: str) -> Diagnosis:
    """Diagnóstico simulado, com 3 hipóteses coerentes entre si e conclusão apontando para a primeira."""
    return Diagnosis(
        hypotheses=[
            Hypothesis(
                id="H1",
                description="Falha de configuração ou de cadastro no lado do cliente.",
                probability_pct=55,
                evidence_for=[f"O relato menciona: {snippet}"],
                evidence_against=["Não há mensagem de erro exata no relato."],
            ),
            Hypothesis(
                id="H2",
                description="Instabilidade temporária do serviço ou da conexão.",
                probability_pct=30,
                evidence_for=["O problema começou de forma recente."],
                evidence_against=["Outros recursos do sistema seguem funcionando."],
            ),
            Hypothesis(
                id="H3",
                description="Limitação do plano ou regra de segurança da conta.",
                probability_pct=15,
                evidence_for=["Não é possível descartar uma regra da conta."],
                evidence_against=["Nenhuma alteração recente de plano foi citada."],
            ),
        ],
        available_evidence=[f"Relato do cliente: {snippet}", "O problema é recente e repetível."],
        missing_information=[
            MissingInfo(item="Mensagem de erro exata", why_it_matters="Aponta direto para a causa provável."),
            MissingInfo(item="Horário da última tentativa", why_it_matters="Permite cruzar com os logs do serviço."),
        ],
        probable_conclusion=Conclusion(
            summary="Mais provável uma falha de configuração do lado do cliente.",
            hypothesis_id="H1",
            confidence=Confidence.MEDIA,
        ),
        customer_summary=f"{SIMULATED_NOTICE} Vamos conferir a configuração e pedir alguns dados para avançar.",
    )


# Schema -> construtor da resposta simulada. As etapas seguintes registram aqui os demais conteúdos.
_BUILDERS: dict[type[BaseModel], Callable[[str], BaseModel]] = {Diagnosis: _diagnosis}


class FakeLLM:
    """``LLMClient`` simulado: determinístico, sem rede e sempre válido pelo schema."""

    def complete(self, messages: Sequence[ChatMessage], schema: type[BaseModel], params: LLMParams) -> LLMResult:
        """Monta a resposta simulada do ``schema`` pedido. Schema sem simulação vira ``ValidationFailed``."""
        started = time.perf_counter()
        builder = _BUILDERS.get(schema)
        if builder is None:
            raise ValidationFailed(f"O provedor fake não simula o schema {schema.__name__}.")
        output = builder(_ticket_snippet(messages))
        parsed = output.model_dump(mode="json")
        text = json.dumps(parsed, ensure_ascii=False)
        # Estimativa grosseira (~4 caracteres por token) só para o campo ``usage`` ter valores plausíveis.
        prompt_tokens = sum(len(m["content"]) for m in messages) // 4
        return LLMResult(
            text=text,
            parsed=parsed,
            usage={"prompt_tokens": prompt_tokens, "completion_tokens": len(text) // 4},
            latency_ms=int((time.perf_counter() - started) * 1000),
            model_used=FAKE_MODEL_NAME,
        )
