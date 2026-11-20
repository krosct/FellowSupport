"""Modelos do domínio: enums, perfil de cliente, ticket e schemas de saída.

Os valores dos enums são os do PDF (item 4.1), em pt-BR e com acentuação, porque são exibidos ao usuário e
inseridos nos prompts. Identificadores e chaves JSON ficam em inglês (ADR 0025).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Produto fictício dos tickets, definido uma vez e inserido nos prompts como variável.
PRODUCT_NAME = "NuvemPonto"
PRODUCT_DESCRIPTION = "um sistema em nuvem de controle de ponto e jornada de trabalho"

# Título dado ao ticket digitado à mão (não vem do catálogo).
FREE_TICKET_TITLE = "Ticket digitado"


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


# --- Schemas de saída ------------------------------------------------------------------------------
# O schema do diagnóstico está completo (Etapa 1); os demais seguem como stubs até a Etapa 2.

# Limites do diagnóstico em um único lugar: o schema os valida e o prompt os recebe como variáveis.
DIAGNOSIS_MIN_HYPOTHESES = 2
DIAGNOSIS_MAX_HYPOTHESES = 4
DIAGNOSIS_MAX_MISSING_INFO = 5


class Confidence(_LabeledEnum):
    """Confiança do modelo na conclusão provável. A ordem de declaração vai da menor para a maior."""

    BAIXA = "baixa"
    MEDIA = "média"
    ALTA = "alta"


class _StrictModel(BaseModel):
    """Base dos schemas de saída: campos extras são recusados (``additionalProperties: false`` no JSON Schema,
    exigido pelo modo ``json_schema`` estrito) e textos vazios ou só com espaços são aparados."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Hypothesis(_StrictModel):
    """Uma causa possível do problema, com os sinais do ticket que a sustentam e os que a enfraquecem."""

    id: str = Field(min_length=1, description='Identificador curto e único, como "H1".')
    description: str = Field(min_length=1, description="Causa possível, em uma ou duas frases.")
    probability_pct: int = Field(
        ge=0, le=100, description="Probabilidade estimada em percentual inteiro, de 0 a 100."
    )
    evidence_for: list[str] = Field(description="Sinais do ticket que sustentam a hipótese.")
    evidence_against: list[str] = Field(description="Sinais do ticket que enfraquecem a hipótese.")


class MissingInfo(_StrictModel):
    """Dado que o ticket não traz e que ajudaria a decidir entre as hipóteses."""

    item: str = Field(min_length=1, description="Informação que falta.")
    why_it_matters: str = Field(min_length=1, description="Por que ela muda o diagnóstico.")


class Conclusion(_StrictModel):
    """Hipótese mais provável, com o nível de confiança. Não contém cadeia de raciocínio (item 1 do PDF)."""

    summary: str = Field(min_length=1, description="Conclusão provável em uma ou duas frases.")
    hypothesis_id: str = Field(min_length=1, description="Id da hipótese escolhida, igual ao de uma das hipóteses.")
    confidence: Confidence


class Diagnosis(_StrictModel):
    """Diagnóstico estruturado e verificável: hipóteses, evidências, dados faltantes, conclusão e um resumo
    para o cliente. Deliberadamente sem raciocínio interno do modelo (item 1 do PDF)."""

    hypotheses: list[Hypothesis] = Field(
        min_length=DIAGNOSIS_MIN_HYPOTHESES,
        max_length=DIAGNOSIS_MAX_HYPOTHESES,
        description="Causas possíveis, da mais para a menos provável.",
    )
    available_evidence: list[str] = Field(min_length=1, description="Fatos observáveis que o ticket já informa.")
    missing_information: list[MissingInfo] = Field(
        max_length=DIAGNOSIS_MAX_MISSING_INFO, description="Dados que faltam para fechar o diagnóstico."
    )
    probable_conclusion: Conclusion
    customer_summary: str = Field(
        min_length=1, description="Resumo do diagnóstico para o cliente, no tom adequado ao perfil dele."
    )

    @model_validator(mode="after")
    def _check_references(self) -> Diagnosis:
        """Garante ids de hipótese únicos e uma conclusão que aponta para uma hipótese existente.

        Essas regras cruzadas não cabem no JSON Schema; falhar aqui aciona o reparo com uma mensagem clara.
        """
        ids = [h.id for h in self.hypotheses]
        if len(ids) != len(set(ids)):
            raise ValueError("os ids das hipóteses devem ser únicos")
        if self.probable_conclusion.hypothesis_id not in ids:
            raise ValueError("probable_conclusion.hypothesis_id deve ser o id de uma das hipóteses")
        return self


class ResolutionSteps(BaseModel):
    """Passo a passo de resolução. Etapa 2 define: passos adaptados ao perfil, cada um com resultado
    esperado e o que fazer se falhar."""


class ClarifyingQuestions(BaseModel):
    """Perguntas de esclarecimento priorizadas. Etapa 2 define: de 3 a 5 perguntas com prioridade e motivo."""


class FlowSummary(BaseModel):
    """Resumo do fluxo como árvore de decisão (nós e arestas). Etapa 2 define o grafo; o ASCII é desenhado
    por código (ADR 0008)."""


# --- Registro de execução (contrato em docs/planejamento/01-arquitetura.md) -------------------------

# Versão do formato do arquivo salvo: permite evoluir o JSON sem quebrar execuções antigas.
RUN_SCHEMA_VERSION = 1

RunStatus = Literal["ok", "error"]


class RunTicket(BaseModel):
    """Ticket como foi usado na execução: ``id`` é ``None`` quando o texto foi digitado à mão."""

    id: str | None
    title: str
    text: str


class RunParams(BaseModel):
    """Parâmetros do modelo usados na execução (entram na comparação justa e, depois, na chave de cache)."""

    temperature: float
    max_tokens: int
    structured_mode: str


class RunError(BaseModel):
    """Falha de uma execução com ``status: "error"``: nome da exceção do domínio e mensagem."""

    type: str
    message: str


class RunRecord(BaseModel):
    """Uma execução de geração, gravada em um arquivo JSON (ADR 0009). Execuções com erro também são gravadas,
    mas nunca entram no cache (ADR 0018).

    ``cache_key``, ``cache_hit`` e ``source_run_id`` são preenchidos pela Etapa 3; ``evaluation`` e
    ``llm_evaluation``, pela Etapa 4. Já fazem parte do contrato para o formato não mudar de versão.
    """

    schema_version: int = RUN_SCHEMA_VERSION
    run_id: str
    timestamp: str  # ISO 8601 com o fuso de APP_TIMEZONE
    status: RunStatus
    customer_id: str
    customer_profile: CustomerProfile
    ticket: RunTicket
    content_type: ContentType
    prompt_version: str
    prompt_sha256: str
    provider: str
    model: str  # modelo pedido
    model_used: str | None = None  # modelo efetivo, devolvido pelo provedor
    params: RunParams
    cache_key: str | None = None
    cache_hit: bool = False
    source_run_id: str | None = None
    attempts: int = 1  # 1 = saiu de primeira; 2 = precisou do reparo
    latency_ms: int = 0
    usage: dict[str, int] = Field(default_factory=dict)
    prompt_messages: list[dict[str, str]] = Field(default_factory=list)
    output: dict | None = None
    rendered: str | None = None
    error: RunError | None = None
    evaluation: dict | None = None
    llm_evaluation: dict | None = None


# Mapa tipo de conteúdo -> schema de saída esperado do LLM.
OUTPUT_SCHEMAS: dict[ContentType, type[BaseModel]] = {
    ContentType.DIAGNOSIS: Diagnosis,
    ContentType.RESOLUTION_STEPS: ResolutionSteps,
    ContentType.CLARIFYING_QUESTIONS: ClarifyingQuestions,
    ContentType.FLOW_SUMMARY: FlowSummary,
}
