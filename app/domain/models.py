"""Modelos do domínio: enums, perfil de cliente, ticket e schemas de saída.

Os valores dos enums são em pt-BR e com acentuação, porque são exibidos ao usuário e
inseridos nos prompts. Identificadores e chaves JSON ficam em inglês (ADR 0025).
"""

from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Produto fictício dos tickets, definido uma vez e inserido nos prompts como variável.
PRODUCT_NAME = "NuvemPonto"
PRODUCT_DESCRIPTION = "um sistema em nuvem de controle de ponto e jornada de trabalho"

# Limites do catálogo editável de clientes e tickets (ADR 0037): títulos e nomes cabem numa linha de cartão e o total
# evita crescimento sem fim dos arquivos numa instalação pública. O limite do texto do ticket é
# ``Settings.max_ticket_chars``. Os prefixos dos ids gerados seguem os dos exemplos (``t-2fa``).
TICKET_TITLE_MAX_CHARS = 120
PROFILE_NAME_MAX_CHARS = 60
MAX_CATALOG_TICKETS = 100
MAX_CATALOG_PROFILES = 20
TICKET_ID_PREFIX = "t-"
PROFILE_ID_PREFIX = "c-"


class LabeledEnum(StrEnum):
    """Enum de texto com ``label`` pronto para exibição (primeira letra maiúscula).

    É a base comum de todo enum que a API publica como ``{value, label}``; subclasses podem
    sobrescrever ``label`` quando o rótulo não deriva do valor.
    """

    @property
    def label(self) -> str:
        """Texto de exibição do valor."""
        return self.value[:1].upper() + self.value[1:]


class TechLevel(LabeledEnum):
    """Nível técnico do cliente."""

    LEIGO = "leigo"
    INTERMEDIARIO = "intermediário"
    AVANCADO = "avançado"


class CommStyle(LabeledEnum):
    """Estilo de comunicação preferido pelo cliente."""

    DIRETO = "direto"
    DETALHADO = "detalhado"
    DIDATICO = "didático"


class Channel(LabeledEnum):
    """Canal de atendimento."""

    CHAT = "chat"
    EMAIL = "e-mail"
    TELEFONE = "telefone"


class ContentType(LabeledEnum):
    """Os quatro conteúdos que o sistema gera."""

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


# Opção "todos os tipos" da API, da CLI e do site: não é um ``ContentType``, mas todos a consomem desta definição.
ALL_OPTION_VALUE = "all"
ALL_OPTION_LABEL = "Todos"


class CustomerProfile(BaseModel):
    """Perfil de cliente: quem recebe a resposta e como prefere recebê-la."""

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
# Um schema por tipo de conteúdo. Todos herdam ``_StrictModel`` (sem campos extras) e validam as regras cruzadas.

# Limites do diagnóstico em um único lugar: o schema os valida e o prompt os recebe como variáveis.
DIAGNOSIS_MIN_HYPOTHESES = 2
DIAGNOSIS_MAX_HYPOTHESES = 3
DIAGNOSIS_MAX_MISSING_INFO = 3


class Confidence(LabeledEnum):
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
    """Hipótese mais provável, com o nível de confiança. Não contém cadeia de raciocínio."""

    summary: str = Field(min_length=1, description="Conclusão provável em uma ou duas frases.")
    hypothesis_id: str = Field(min_length=1, description="Id da hipótese escolhida, igual ao de uma das hipóteses.")
    confidence: Confidence


class Diagnosis(_StrictModel):
    """Diagnóstico estruturado e verificável: hipóteses, evidências, dados faltantes, conclusão e um resumo
    para o cliente. Deliberadamente sem raciocínio interno do modelo."""

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
    def _check_references(self) -> Self:
        """Garante ids de hipótese únicos e uma conclusão que aponta para uma hipótese existente.

        Essas regras cruzadas não cabem no JSON Schema; falhar aqui aciona o reparo com uma mensagem clara.
        """
        # Garante ids únicos nas hipóteses e referência válida na conclusão.
        ids = [h.id for h in self.hypotheses]
        if len(ids) != len(set(ids)):
            raise ValueError("os ids das hipóteses devem ser únicos")
        if self.probable_conclusion.hypothesis_id not in ids:
            raise ValueError("probable_conclusion.hypothesis_id deve ser o id de uma das hipóteses")
        return self


# --- Passo a passo de resolução -----------------------------------------------------------------------
# Limites em um único lugar: o schema os valida e o prompt os recebe como variáveis.
STEPS_MIN = 2
STEPS_MAX = 6


class ResolutionStep(_StrictModel):
    """Um passo executável: o que fazer, o que se espera ver e o que fazer se não funcionar."""

    order: int = Field(ge=1, description="Posição do passo, a partir de 1, sem repetir nem pular números.")
    title: str = Field(min_length=1, description="Título curto do passo.")
    instruction: str = Field(min_length=1, description="O que o cliente deve fazer, na linguagem do perfil.")
    expected_result: str = Field(min_length=1, description="O que o cliente deve observar se o passo der certo.")
    if_it_fails: str = Field(min_length=1, description="O que fazer se o resultado esperado não aparecer.")


class ResolutionSteps(_StrictModel):
    """Passo a passo de resolução adaptado ao perfil: abertura, passos verificáveis, critério de escalonamento
    e fechamento. Cada passo traz resultado esperado e plano B, para o cliente saber se avançou."""

    opening: str = Field(min_length=1, description="Abertura curta que contextualiza o atendimento.")
    steps: list[ResolutionStep] = Field(
        min_length=STEPS_MIN, max_length=STEPS_MAX, description="Passos na ordem em que devem ser executados."
    )
    when_to_escalate: str = Field(
        min_length=1, description="Em que situação o caso deve ser escalado a outro nível, e para quem."
    )
    closing: str = Field(min_length=1, description="Fechamento curto, com a próxima ação combinada.")

    @model_validator(mode="after")
    def _check_order(self) -> Self:
        """Exige a numeração 1, 2, 3... na ordem em que os passos aparecem (a interface mostra ``order``)."""
        # Garante que os passos estejam numerados em sequência a partir de 1.
        if [step.order for step in self.steps] != list(range(1, len(self.steps) + 1)):
            raise ValueError("steps[].order deve ser 1, 2, 3... na ordem em que os passos aparecem")
        return self


# --- Perguntas de esclarecimento ----------------------------------------------------------------------
QUESTIONS_MIN = 2
QUESTIONS_MAX = 4


class ClarifyingQuestion(_StrictModel):
    """Uma pergunta ao cliente, com o motivo e o que a resposta destrava."""

    priority: int = Field(ge=1, description="Prioridade a partir de 1 (1 = a mais importante), sem repetir.")
    question: str = Field(min_length=1, description="A pergunta, em uma frase, pedindo uma só informação.")
    why_it_matters: str = Field(min_length=1, description="Por que a resposta é necessária para avançar.")
    unlocks: str = Field(min_length=1, description="Qual hipótese ou dúvida a resposta ajuda a confirmar ou descartar.")


class ClarifyingQuestions(_StrictModel):
    """Perguntas de esclarecimento priorizadas: só o necessário para avançar o atendimento."""

    questions: list[ClarifyingQuestion] = Field(
        min_length=QUESTIONS_MIN, max_length=QUESTIONS_MAX, description="Da mais para a menos prioritária."
    )
    can_proceed_without_answers: bool = Field(
        description="Verdadeiro se o atendimento consegue avançar com o que já se sabe, sem as respostas."
    )
    proceed_note: str = Field(
        min_length=1, description="Em uma frase: o que dá para fazer já, ou por que as respostas são indispensáveis."
    )

    @model_validator(mode="after")
    def _check_priorities(self) -> Self:
        """Exige prioridades 1, 2, 3... na ordem em que as perguntas aparecem (a mais importante primeiro)."""
        # Garante prioridades sequenciais 1..N na ordem em que foram listadas.
        if [q.priority for q in self.questions] != list(range(1, len(self.questions) + 1)):
            raise ValueError("questions[].priority deve ser 1, 2, 3... na ordem em que as perguntas aparecem")
        return self


# --- Resumo visual do fluxo (árvore de decisão) -------------------------------------------------------
FLOW_MIN_NODES = 3
FLOW_MAX_NODES = 14
FLOW_LABEL_MAX_CHARS = 100


class FlowNodeType(StrEnum):
    """Tipos de nó do fluxograma: início, ação, decisão (pergunta com ramos) e fim."""

    START = "start"
    ACTION = "action"
    DECISION = "decision"
    END = "end"


class FlowNode(_StrictModel):
    """Um nó do fluxo."""

    id: str = Field(min_length=1, description='Identificador único e curto, como "n1".')
    type: FlowNodeType
    label: str = Field(min_length=1, max_length=FLOW_LABEL_MAX_CHARS, description="Texto curto do nó.")


class FlowEdge(_StrictModel):
    """Aresta dirigida entre dois nós. Nas decisões o rótulo nomeia o ramo (por exemplo, Sim ou Não)."""

    source: str = Field(min_length=1, description="Id do nó de origem.")
    target: str = Field(min_length=1, description="Id do nó de destino.")
    label: str = Field(description="Rótulo do ramo; obrigatório quando a origem é uma decisão, vazio nos demais.")


class FlowSummary(_StrictModel):
    """Resumo do fluxo como árvore de decisão (nós e arestas). O ASCII é desenhado por código a partir daqui
    (ADR 0008), então a estrutura precisa ser íntegra: o validador rejeita o que o desenho não saberia mostrar."""

    nodes: list[FlowNode] = Field(min_length=FLOW_MIN_NODES, max_length=FLOW_MAX_NODES)
    edges: list[FlowEdge] = Field(min_length=FLOW_MIN_NODES - 1)

    @model_validator(mode="after")
    def _check_integrity(self) -> Self:
        """Valida ids únicos, um único ``start``, arestas com extremos existentes, grau de cada tipo de nó,
        alcance a partir do início e ausência de ciclos. Regras cruzadas não cabem no JSON Schema; falhar aqui
        aciona o reparo com a mensagem exata do problema."""
        # Confere ids únicos, presença de exatamente um nó start e ao menos um end.
        ids = [node.id for node in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("os ids dos nós devem ser únicos")
        known = set(ids)

        starts = [n for n in self.nodes if n.type is FlowNodeType.START]
        if len(starts) != 1:
            raise ValueError(f"deve haver exatamente um nó start (há {len(starts)})")
        if not any(n.type is FlowNodeType.END for n in self.nodes):
            raise ValueError("deve haver ao menos um nó end")

        # Mapeia entradas e saídas garantindo extremos existentes e sem auto-laço.
        outgoing: dict[str, list[FlowEdge]] = {node_id: [] for node_id in ids}
        incoming: dict[str, int] = dict.fromkeys(ids, 0)
        for edge in self.edges:
            for end_name, end_id in (("origem", edge.source), ("destino", edge.target)):
                if end_id not in known:
                    raise ValueError(f"aresta com {end_name} inexistente: {end_id!r}")
            if edge.source == edge.target:
                raise ValueError(f"aresta de {edge.source!r} para ele mesmo")
            outgoing[edge.source].append(edge)
            incoming[edge.target] += 1

        # Valida grau de entrada/saída por tipo e rótulos distintos nas decisões.
        for node in self.nodes:
            out = outgoing[node.id]
            if node.type is FlowNodeType.START and incoming[node.id]:
                raise ValueError("o nó start não pode receber arestas")
            if node.type is FlowNodeType.END and out:
                raise ValueError(f"o nó end {node.id!r} não pode ter arestas de saída")
            if node.type in (FlowNodeType.START, FlowNodeType.ACTION) and len(out) != 1:
                raise ValueError(f"o nó {node.type.value} {node.id!r} deve ter exatamente 1 aresta de saída")
            if node.type is FlowNodeType.DECISION:
                if len(out) < 2:
                    raise ValueError(f"a decisão {node.id!r} deve ter ao menos 2 ramos")
                labels = [edge.label.strip().casefold() for edge in out]
                if not all(labels):
                    raise ValueError(f"os ramos da decisão {node.id!r} devem ter rótulo (Sim ou Não)")
                if len(labels) != len(set(labels)):
                    raise ValueError(f"os ramos da decisão {node.id!r} devem ter rótulos diferentes")

        # Busca em profundidade com três cores: aresta para um nó "em visita" fecha um ciclo.
        state: dict[str, int] = {}  # 1 = em visita, 2 = concluído
        stack: list[tuple[str, int]] = [(starts[0].id, 0)]
        state[starts[0].id] = 1
        while stack:
            node_id, index = stack.pop()
            if index < len(outgoing[node_id]):
                stack.append((node_id, index + 1))
                target = outgoing[node_id][index].target
                if state.get(target) == 1:
                    raise ValueError(f"o fluxo tem um ciclo passando por {target!r}")
                if target not in state:
                    state[target] = 1
                    stack.append((target, 0))
            else:
                state[node_id] = 2
        unreachable = [node_id for node_id in ids if node_id not in state]
        if unreachable:
            raise ValueError(f"nós não alcançáveis a partir do start: {', '.join(unreachable)}")
        return self


# --- Registro de execução (contrato em docs/planejamento/01-arquitetura.md) -------------------------

# Versão do formato do arquivo salvo: permite evoluir o JSON sem quebrar execuções antigas.
RUN_SCHEMA_VERSION = 1

RunStatus = Literal["ok", "error"]

# Identificador curto da execução (parte do nome do arquivo salvo): 12 caracteres hexadecimais. O padrão também
# valida o id vindo de fora (URL, CLI) antes de ele virar parte de um caminho ou de um glob.
RUN_ID_LENGTH = 12
RUN_ID_PATTERN = rf"[0-9a-f]{{{RUN_ID_LENGTH}}}"

# Chave de cache: SHA-256 em hexadecimal (64 caracteres), também usada como nome do arquivo em ``var/cache/``.
CACHE_KEY_PATTERN = r"[0-9a-f]{64}"


class RunTicket(BaseModel):
    """Ticket como foi usado na execução: uma cópia do ticket do catálogo naquele momento (editá-lo depois não muda
    a execução)."""

    id: str
    title: str
    text: str


class RunParams(BaseModel):
    """Parâmetros do modelo usados na execução (entram na comparação justa e, depois, na chave de cache)."""

    temperature: float
    max_tokens: int
    structured_mode: str
    reasoning: str = "default"  # controle de raciocínio (ADR 0027); "default" também nos arquivos antigos


class LlmCall(BaseModel):
    """Uma chamada ao LLM dentro da execução (a original e, se houver, a de reparo), para depurar quem atendeu.

    O OpenRouter roteia o mesmo modelo entre vários provedores, e um deles pode se comportar diferente (por exemplo,
    cortar a resposta abaixo do ``max_tokens``): ``provider_used`` e ``response_id`` permitem achar o culpado e
    consultar a geração no provedor (ADR 0042).
    """

    attempt: int = Field(description="1 = chamada original; 2 = reparo.")
    model_used: str = ""
    provider_used: str = ""
    response_id: str = ""
    finish_reason: str = ""
    latency_ms: int = 0
    usage: dict[str, int] = Field(default_factory=dict)
    json_extracted: bool = Field(description="Se havia um objeto JSON aproveitável no texto.")
    problem: str | None = Field(default=None, description="Por que a saída foi recusada; None se foi aceita.")


class RunError(BaseModel):
    """Falha de uma execução com ``status: "error"``: nome da exceção do domínio e mensagem."""

    type: str
    message: str


class RunRecord(BaseModel):
    """Uma execução de geração, gravada em um arquivo JSON (ADR 0009). Execuções com erro também são gravadas,
    mas nunca entram no cache (ADR 0018).

    ``cache_key`` vai em toda execução (inclusive com erro e com o cache desligado), para localizar execuções
    equivalentes. ``cache_hit`` e ``source_run_id`` marcam o reaproveitamento (ADR 0028). ``evaluation`` fica vazio
    até a avaliação manual (ADR 0020).
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
    attempts: int = 1  # chamadas ao LLM: 0 = cache hit; 1 = saiu de primeira; 2 = precisou do reparo
    latency_ms: int = 0
    usage: dict[str, int] = Field(default_factory=dict)
    llm_calls: list[LlmCall] = Field(default_factory=list)  # detalhe por chamada; vazio no cache hit e nos antigos
    prompt_messages: list[dict[str, str]] = Field(default_factory=list)
    output: dict | None = None
    rendered: str | None = None
    error: RunError | None = None
    evaluation: dict | None = None


class CacheEntry(BaseModel):
    """Entrada do cache: aponta da chave para a execução de origem, que guarda a saída (ADR 0010 e 0028).

    O cache não duplica a saída: um único registro de execução continua sendo a fonte da verdade.
    """

    cache_key: str
    source_run_id: str
    created_at: str  # ISO 8601 com o fuso de APP_TIMEZONE


class CacheConflict(BaseModel):
    """Uma entrada de cache que o pedido atual substituiria (ADR 0035 e 0036).

    ``run_id`` é a execução que hoje é a origem da chave e ``created_at`` é o momento em que essa entrada foi
    gravada (ISO 8601 com o fuso de ``APP_TIMEZONE``).
    """

    content_type: ContentType
    prompt_version: str
    run_id: str
    created_at: str | None = None

    def describe(self) -> str:
        """Frase curta, em pt-BR, para o terminal e para a mensagem do erro."""
        when = f", de {self.created_at[:16].replace('T', ' ')}" if self.created_at else ""
        return f"{self.content_type.label} {self.prompt_version}: origem do cache é a execução {self.run_id}{when}"


# Mapa tipo de conteúdo -> schema de saída esperado do LLM.
OUTPUT_SCHEMAS: dict[ContentType, type[BaseModel]] = {
    ContentType.DIAGNOSIS: Diagnosis,
    ContentType.RESOLUTION_STEPS: ResolutionSteps,
    ContentType.CLARIFYING_QUESTIONS: ClarifyingQuestions,
    ContentType.FLOW_SUMMARY: FlowSummary,
}
