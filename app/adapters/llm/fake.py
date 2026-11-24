"""Provedor de LLM simulado (ADR 0023): responde sem rede, sem chave e sem custo.

Devolve sempre o mesmo JSON, válido pelo schema pedido, para a mesma entrada. Serve para rodar o projeto inteiro
offline, para a demonstração e para os testes. As respostas são marcadas como simuladas: elas provam o fluxo,
não a qualidade de um modelo real.
"""

import json
import re
import time
from collections.abc import Callable, Sequence

from pydantic import BaseModel

from app.domain.errors import ValidationFailed
from app.domain.models import (
    ClarifyingQuestion,
    ClarifyingQuestions,
    Conclusion,
    Confidence,
    Diagnosis,
    FlowEdge,
    FlowNode,
    FlowNodeType,
    FlowSummary,
    Hypothesis,
    MissingInfo,
    ResolutionStep,
    ResolutionSteps,
)
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
    # Procura do fim para o começo a última mensagem que contenha <ticket>.
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


def _resolution_steps(snippet: str) -> ResolutionSteps:
    """Passo a passo simulado, em frases corridas (sem markdown), válido para qualquer canal."""
    return ResolutionSteps(
        opening=f"{SIMULATED_NOTICE} Entendi o problema e vamos resolver juntos, um passo de cada vez.",
        steps=[
            ResolutionStep(
                order=1,
                title="Conferir os dados do cadastro",
                instruction="Abra o seu cadastro e confira se o número de contato e o e-mail estão corretos.",
                expected_result="Os dados aparecem exatamente como você os conhece.",
                if_it_fails="Corrija o dado que estiver errado e salve a alteração.",
            ),
            ResolutionStep(
                order=2,
                title="Repetir a ação com calma",
                instruction="Tente de novo a ação que não funcionou e observe a mensagem que aparece.",
                expected_result="A ação é concluída sem mensagem de erro.",
                if_it_fails="Anote a mensagem exata que apareceu e passe para o próximo passo.",
            ),
            ResolutionStep(
                order=3,
                title="Pedir ajuda com os detalhes",
                instruction="Conte para o atendimento a mensagem que apareceu e o horário da tentativa.",
                expected_result="O atendimento confirma que recebeu as informações.",
                if_it_fails="Peça para falar com um especialista.",
            ),
        ],
        when_to_escalate="Escale para o nível 3 se o problema seguir após o passo 3 ou houver risco de perder dados.",
        closing="Qualquer novidade, é só me chamar que seguimos daqui.",
    )


def _clarifying_questions(snippet: str) -> ClarifyingQuestions:
    """Quatro perguntas simuladas, já em ordem de prioridade."""
    return ClarifyingQuestions(
        questions=[
            ClarifyingQuestion(
                priority=1,
                question="Qual é a mensagem exata que aparece quando o problema acontece?",
                why_it_matters="A mensagem aponta direto para a causa mais provável.",
                unlocks="Confirma ou descarta a hipótese H1.",
            ),
            ClarifyingQuestion(
                priority=2,
                question="A que horas foi a última tentativa?",
                why_it_matters="Permite cruzar o relato com os registros do serviço.",
                unlocks="Separa uma falha temporária de um problema de configuração.",
            ),
            ClarifyingQuestion(
                priority=3,
                question="Isso acontece com outras pessoas da sua equipe?",
                why_it_matters="Mostra se o problema é da conta inteira ou de um só usuário.",
                unlocks="Descarta a hipótese de limitação da conta.",
            ),
            ClarifyingQuestion(
                priority=4,
                question="Houve alguma mudança recente no seu cadastro ou no seu aparelho?",
                why_it_matters="Mudanças recentes costumam ser a origem do problema.",
                unlocks="Confirma a hipótese de falha de configuração.",
            ),
        ],
        can_proceed_without_answers=True,
        proceed_note=f"{SIMULATED_NOTICE} Dá para começar pela conferência do cadastro enquanto as respostas chegam.",
    )


def _flow_summary(snippet: str) -> FlowSummary:
    """Fluxo simulado com decisão, ramos que convergem em um mesmo fim e um escalonamento."""
    nodes = [
        ("n1", FlowNodeType.START, "Cliente relata o problema"),
        ("n2", FlowNodeType.DECISION, "Os dados do cadastro estão corretos?"),
        ("n3", FlowNodeType.ACTION, "Corrigir os dados do cadastro"),
        ("n4", FlowNodeType.DECISION, "A ação funciona ao repetir?"),
        ("n5", FlowNodeType.ACTION, "Coletar a mensagem de erro e o horário"),
        ("n6", FlowNodeType.END, "Problema resolvido"),
        ("n7", FlowNodeType.END, "Escalar para o nível 3 com os detalhes"),
    ]
    edges = [
        ("n1", "n2", ""), ("n2", "n3", "Não"), ("n2", "n4", "Sim"), ("n3", "n4", ""),
        ("n4", "n6", "Sim"), ("n4", "n5", "Não"), ("n5", "n7", ""),
    ]
    return FlowSummary(
        nodes=[FlowNode(id=i, type=t, label=label) for i, t, label in nodes],
        edges=[FlowEdge(source=a, target=b, label=label) for a, b, label in edges],
    )


# Schema -> construtor da resposta simulada, um por tipo de conteúdo.
_BUILDERS: dict[type[BaseModel], Callable[[str], BaseModel]] = {
    Diagnosis: _diagnosis,
    ResolutionSteps: _resolution_steps,
    ClarifyingQuestions: _clarifying_questions,
    FlowSummary: _flow_summary,
}


class FakeLLM:
    """``LLMClient`` simulado: determinístico, sem rede e sempre válido pelo schema."""

    def complete(self, messages: Sequence[ChatMessage], schema: type[BaseModel], params: LLMParams) -> LLMResult:
        """Monta a resposta simulada do ``schema`` pedido. Schema sem simulação vira ``ValidationFailed``."""
        # Localiza o construtor simulado pelo schema, gera a saída e estima tokens.
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
            finish_reason="stop",
            provider_used=FAKE_MODEL_NAME,
        )
