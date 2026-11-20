"""Modelos do domínio: enums, perfil de cliente, ticket e schemas de saída.

Os valores dos enums são os do PDF (item 4.1), em pt-BR e com acentuação, porque são exibidos ao usuário e
inseridos nos prompts. Identificadores e chaves JSON ficam em inglês (ADR 0025).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class _LabeledEnum(StrEnum):
    """Enum de texto com ``label`` pronto para exibição (primeira letra maiúscula)."""

    @property
    def label(self) -> str:
        return self.value[:1].upper() + self.value[1:]


class TechLevel(_LabeledEnum):
    """Nível técnico do cliente."""

    LEIGO = "leigo"
    INTERMEDIARIO = "intermediário"
    AVANCADO = "avançado"


class CommStyle(_LabeledEnum):
    """Estilo de comunicação preferido pelo cliente."""

    DIRETO = "direto"
    DETALHADO = "detalhado"
    DIDATICO = "didático"


class Channel(_LabeledEnum):
    """Canal de atendimento."""

    CHAT = "chat"
    EMAIL = "e-mail"
    TELEFONE = "telefone"


class ContentType(StrEnum):
    """Os quatro conteúdos que o sistema gera (item 1 do PDF)."""

    DIAGNOSIS = "diagnosis"
    RESOLUTION_STEPS = "resolution_steps"
    CLARIFYING_QUESTIONS = "clarifying_questions"
    FLOW_SUMMARY = "flow_summary"

    @property
    def label(self) -> str:
        """Rótulo em pt-BR exibido na interface."""
        return _CONTENT_TYPE_LABELS[self]


# Rótulos em um único lugar (SSOT); a API os publica em /api/meta.
_CONTENT_TYPE_LABELS: dict[ContentType, str] = {
    ContentType.DIAGNOSIS: "Diagnóstico",
    ContentType.RESOLUTION_STEPS: "Passo a passo",
    ContentType.CLARIFYING_QUESTIONS: "Perguntas de esclarecimento",
    ContentType.FLOW_SUMMARY: "Resumo visual do fluxo",
}


class CustomerProfile(BaseModel):
    """Perfil de cliente (item 4.1 do PDF): quem recebe a resposta e como prefere recebê-la."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1, description="Identificador estável, usado nos JSONs e na CLI.")
    name: str = Field(min_length=1, description="Nome de exibição.")
    tech_level: TechLevel
    comm_style: CommStyle
    channel: Channel


class Ticket(BaseModel):
    """Problema relatado por um cliente."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    text: str = Field(min_length=1, description="Relato original, tratado sempre como dado (ADR 0022).")


# --- Schemas de saída (stubs documentados) ---------------------------------------------------------
# As Etapas 1 e 2 completam os campos. Já ficam declarados para o mapa tipo -> schema existir desde já.


class Diagnosis(BaseModel):
    """Diagnóstico estruturado. Etapa 1 define: hipóteses, evidências (a favor e contra), dados faltantes e
    conclusão provável com nível de confiança. Sem cadeia de raciocínio (item 1 do PDF)."""


class ResolutionSteps(BaseModel):
    """Passo a passo de resolução. Etapa 2 define: passos adaptados ao perfil, cada um com resultado
    esperado e o que fazer se falhar."""


class ClarifyingQuestions(BaseModel):
    """Perguntas de esclarecimento priorizadas. Etapa 2 define: de 3 a 5 perguntas com prioridade e motivo."""


class FlowSummary(BaseModel):
    """Resumo do fluxo como árvore de decisão (nós e arestas). Etapa 2 define o grafo; o ASCII é desenhado
    por código (ADR 0008)."""


# Mapa tipo de conteúdo -> schema de saída esperado do LLM.
OUTPUT_SCHEMAS: dict[ContentType, type[BaseModel]] = {
    ContentType.DIAGNOSIS: Diagnosis,
    ContentType.RESOLUTION_STEPS: ResolutionSteps,
    ContentType.CLARIFYING_QUESTIONS: ClarifyingQuestions,
    ContentType.FLOW_SUMMARY: FlowSummary,
}
