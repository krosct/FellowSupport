"""Motor de prompts (ADR 0005): monta as mensagens de chat a partir de perfil, ticket, tipo e versão.

Os textos moram em arquivos versionados (``prompts/<versão>/``) e são preenchidos com ``string.Template``. A
lógica de adaptação ao perfil fica em dados (``adaptation.json``), não dentro dos templates. Montagem:

- mensagem ``system``: ``system.md`` (persona, limites e defesa contra injeção, ADR 0022);
- mensagem ``user``: ``context.md`` (perfil e ticket) seguido do prompt do tipo (ex.: ``diagnosis.md``).
"""

import json
import re
from collections.abc import Mapping, Sequence
from string import Template

from app.domain.channel_rules import channel_format_instruction
from app.domain.errors import NotFound, ValidationFailed
from app.domain.models import (
    DIAGNOSIS_MAX_HYPOTHESES,
    DIAGNOSIS_MAX_MISSING_INFO,
    DIAGNOSIS_MIN_HYPOTHESES,
    FLOW_LABEL_MAX_CHARS,
    FLOW_MAX_NODES,
    FLOW_MIN_NODES,
    PRODUCT_DESCRIPTION,
    PRODUCT_NAME,
    QUESTIONS_MAX,
    QUESTIONS_MIN,
    STEPS_MAX,
    STEPS_MIN,
    Channel,
    CommStyle,
    Confidence,
    ContentType,
    CustomerProfile,
    TechLevel,
)
from app.domain.prompting.registry import (
    PROMPT_FILE_MAX_CHARS,
    PromptRegistry,
    is_valid_prompt_filename,
)
from app.ports.llm import ChatMessage

# Arquivos fixos de cada versão. O prompt de cada tipo de conteúdo é ``<content_type>.md``.
SYSTEM_FILE = "system.md"
CONTEXT_FILE = "context.md"
ADAPTATION_FILE = "adaptation.json"
REPAIR_FILE = "repair.md"

# Dimensões do perfil cobertas por ``adaptation.json``: nome do campo no perfil -> enum com os valores válidos.
ADAPTATION_DIMENSIONS = {"tech_level": TechLevel, "comm_style": CommStyle, "channel": Channel}

# Variáveis conhecidas pelos templates de prompt e de reparo (SSOT).
BASE_TEMPLATE_VARIABLES: frozenset[str] = frozenset(
    {"product_name", "product_description", "customer_name", "ticket_text", "channel_format", *ADAPTATION_DIMENSIONS}
)
REPAIR_TEMPLATE_VARIABLES: frozenset[str] = frozenset({"error"})

# Tag que delimita dados não confiáveis no prompt: o relato do cliente (``<ticket>``, ADR 0022). Ocorrências dela
# dentro do próprio texto são neutralizadas, para o conteúdo não "fechar" o bloco e escapar da delimitação.
TICKET_OPEN, TICKET_CLOSE = "<ticket>", "</ticket>"
_DELIMITER_TAG = re.compile(r"</?\s*ticket\s*>", re.IGNORECASE)

# Limite do que se devolve ao modelo, no reparo, da resposta anterior dele (mantém o prompt curto).
MAX_REPAIR_ECHO_CHARS = 6000

# Variáveis extras, por tipo de conteúdo, tiradas das constantes do schema (SSOT: o prompt e a validação
# usam os mesmos números).
_TYPE_VARIABLES: dict[ContentType, dict[str, str]] = {
    ContentType.DIAGNOSIS: {
        "min_hypotheses": str(DIAGNOSIS_MIN_HYPOTHESES),
        "max_hypotheses": str(DIAGNOSIS_MAX_HYPOTHESES),
        "max_missing_info": str(DIAGNOSIS_MAX_MISSING_INFO),
        "confidence_levels": ", ".join(f'"{c.value}"' for c in Confidence),
    },
    ContentType.RESOLUTION_STEPS: {"min_steps": str(STEPS_MIN), "max_steps": str(STEPS_MAX)},
    ContentType.CLARIFYING_QUESTIONS: {"min_questions": str(QUESTIONS_MIN), "max_questions": str(QUESTIONS_MAX)},
    ContentType.FLOW_SUMMARY: {
        "min_nodes": str(FLOW_MIN_NODES),
        "max_nodes": str(FLOW_MAX_NODES),
        "label_max_chars": str(FLOW_LABEL_MAX_CHARS),
    },
}


def type_prompt_file(content_type: ContentType) -> str:
    """Nome do arquivo de prompt de um tipo de conteúdo (``diagnosis`` -> ``diagnosis.md``)."""
    return f"{content_type.value}.md"


# Os 8 arquivos de conteúdo obrigatórios em toda versão (somados ao meta.json = 9 arquivos da pasta).
REQUIRED_PROMPT_FILES: frozenset[str] = frozenset(
    {SYSTEM_FILE, CONTEXT_FILE, ADAPTATION_FILE, REPAIR_FILE, *(type_prompt_file(t) for t in ContentType)}
)

_TYPE_FILE_VARIABLES: dict[str, frozenset[str]] = {
    type_prompt_file(content_type): BASE_TEMPLATE_VARIABLES | set(variables)
    for content_type, variables in _TYPE_VARIABLES.items()
}


def neutralize_delimiters(text: str) -> str:
    """Troca as tags ``<ticket>`` (abrindo ou fechando) por ``[ticket]``."""
    return _DELIMITER_TAG.sub("[ticket]", text)


def render_template(filename: str, template: str, variables: Mapping[str, str]) -> str:
    """Preenche o template. Placeholder sem valor ou ``$`` solto viram ``ValidationFailed`` com o arquivo.

    ``Template.substitute`` faz uma única passada: ``$`` dentro do texto do ticket não é reinterpretado.
    """
    # Substitui placeholders em passada única e converte erros para ValidationFailed.
    try:
        return Template(template).substitute(variables)
    except KeyError as exc:
        raise ValidationFailed(f"Placeholder sem valor em {filename}: {exc}") from exc
    except ValueError as exc:
        raise ValidationFailed(f"Placeholder inválido em {filename}: {exc}") from exc


def validate_adaptation_payload(data: object, label: str) -> dict[str, dict[str, str]]:
    """Confere se ``adaptation.json`` é um objeto válido cobrindo nível técnico, estilo e canal."""
    for dimension, enum_cls in ADAPTATION_DIMENSIONS.items():
        rules = data.get(dimension) if isinstance(data, dict) else None
        missing = [m.value for m in enum_cls if not isinstance(rules, dict) or m.value not in rules]
        if missing:
            raise ValidationFailed(f"{label} sem texto para {dimension}: {', '.join(missing)}")
        for member in enum_cls:
            val = rules[member.value]  # type: ignore[index]
            if not isinstance(val, str) or not val.strip():
                raise ValidationFailed(f"{label} tem texto vazio em {dimension}.{member.value}.")
    return data  # type: ignore[return-value]


def validate_prompt_files(files: Mapping[str, str]) -> dict[str, str]:
    """Normaliza quebras de linha e valida todos os 8 arquivos obrigatórios, ``adaptation.json`` e placeholders.

    Com o ``meta.json`` validado e gravado na criação, garante a integridade dos 9 arquivos da versão.
    """
    if not files:
        raise ValidationFailed("Informe ao menos um arquivo de prompt.")

    normalized: dict[str, str] = {}
    for raw_name, raw_content in files.items():
        name = raw_name.strip()
        if not is_valid_prompt_filename(name):
            raise ValidationFailed(f"Nome de arquivo de prompt inválido: {raw_name!r}.")
        if name in normalized:
            raise ValidationFailed(f"Arquivo de prompt duplicado: {name}.")
        if not isinstance(raw_content, str):
            raise ValidationFailed(f"O conteúdo de {name} deve ser texto.")
        content = raw_content.replace("\r\n", "\n")
        if not content.strip():
            raise ValidationFailed(f"O arquivo {name} não pode ficar vazio.")
        if len(content) > PROMPT_FILE_MAX_CHARS:
            raise ValidationFailed(f"O arquivo {name} passa do limite de {PROMPT_FILE_MAX_CHARS} caracteres.")
        normalized[name] = content

    missing = sorted(REQUIRED_PROMPT_FILES - set(normalized))
    if missing:
        raise ValidationFailed(f"Faltam arquivos obrigatórios do prompt: {', '.join(missing)}.")

    try:
        data = json.loads(normalized[ADAPTATION_FILE])
    except json.JSONDecodeError as exc:
        raise ValidationFailed(f"JSON inválido em {ADAPTATION_FILE}: {exc}") from exc
    validate_adaptation_payload(data, ADAPTATION_FILE)

    for name, content in normalized.items():
        if not name.endswith(".md"):
            continue
        tpl = Template(content)
        if not tpl.is_valid():
            raise ValidationFailed(
                f"Placeholder inválido em {name}: use $$ para cifrão literal ou $variavel válida."
            )
        if name == REPAIR_FILE:
            allowed = REPAIR_TEMPLATE_VARIABLES
        else:
            allowed = _TYPE_FILE_VARIABLES.get(name, BASE_TEMPLATE_VARIABLES)
        unknown = [ident for ident in tpl.get_identifiers() if ident not in allowed]
        if unknown:
            raise ValidationFailed(f"Placeholder desconhecido em {name}: {', '.join(unknown)}.")

    return normalized


class PromptBuilder:
    """Monta as mensagens de cada geração a partir de uma versão de prompt do registro."""

    def __init__(self, registry: PromptRegistry) -> None:
        self._registry = registry

    def _adaptation_from(self, version: str, raw_adaptation: str) -> dict[str, dict[str, str]]:
        """Decodifica e valida o texto de ``adaptation.json`` já carregado no snapshot."""
        try:
            data = json.loads(raw_adaptation)
        except json.JSONDecodeError as exc:
            raise ValidationFailed(f"JSON inválido em {version}/{ADAPTATION_FILE}: {exc}") from exc
        return validate_adaptation_payload(data, f"{version}/{ADAPTATION_FILE}")

    def _adaptation(self, version: str) -> dict[str, dict[str, str]]:
        """Lê ``adaptation.json`` e confere que cobre todos os valores de nível, estilo e canal."""
        return self._adaptation_from(version, self._registry.read(version, ADAPTATION_FILE))

    def build_with_hash(
        self, version: str, content_type: ContentType, profile: CustomerProfile, ticket_text: str
    ) -> tuple[list[ChatMessage], str]:
        """Monta ``([system, user], prompt_sha256)`` a partir de um único snapshot dos arquivos da versão."""
        files, prompt_sha256 = self._registry.snapshot(version)
        type_file = type_prompt_file(content_type)
        if type_file not in files:
            raise NotFound(f"A versão {version} não tem prompt para {content_type.value} ({type_file})")
        for required_file in (ADAPTATION_FILE, SYSTEM_FILE, CONTEXT_FILE):
            if required_file not in files:
                raise NotFound(f"Arquivo de prompt não encontrado: {version}/{required_file}")

        adaptation = self._adaptation_from(version, files[ADAPTATION_FILE])
        variables: dict[str, str] = {
            "product_name": PRODUCT_NAME,
            "product_description": PRODUCT_DESCRIPTION,
            "customer_name": profile.name,
            "ticket_text": neutralize_delimiters(ticket_text).strip(),
            "channel_format": channel_format_instruction(profile.channel),
            **_TYPE_VARIABLES.get(content_type, {}),
        }
        for dimension in ADAPTATION_DIMENSIONS:
            variables[dimension] = adaptation[dimension][getattr(profile, dimension).value]

        system = render_template(SYSTEM_FILE, files[SYSTEM_FILE], variables)
        context = render_template(CONTEXT_FILE, files[CONTEXT_FILE], variables)
        task = render_template(type_file, files[type_file], variables)
        messages: list[ChatMessage] = [
            {"role": "system", "content": system.strip()},
            {"role": "user", "content": f"{context.strip()}\n\n{task.strip()}"},
        ]
        return messages, prompt_sha256

    def build(
        self, version: str, content_type: ContentType, profile: CustomerProfile, ticket_text: str
    ) -> list[ChatMessage]:
        """Mensagens ``[system, user]`` da geração de ``content_type`` na ``version`` de prompt.

        Variáveis disponíveis nos templates: ``product_name``, ``product_description``, ``customer_name``,
        ``tech_level``, ``comm_style``, ``channel`` (texto de ``adaptation.json`` para o valor do perfil),
        ``channel_format`` (restrição de formato do canal, de ``channel_rules``), ``ticket_text`` e as variáveis
        do tipo (ex.: ``min_hypotheses``, ``min_steps``, ``max_nodes``).
        """
        messages, _ = self.build_with_hash(version, content_type, profile, ticket_text)
        return messages

    def build_repair(
        self, version: str, messages: Sequence[ChatMessage], previous_output: str, error: str
    ) -> list[ChatMessage]:
        """Mensagens da tentativa de reparo (ADR 0004): o pedido original, a resposta inválida e o erro.

        A resposta anterior entra como mensagem do ``assistant`` (truncada) e o erro de validação, sem eco dos
        valores, vai no ``repair.md``.
        """
        # Ecoa a saída inválida truncada e envia a instrução de correção com o erro.
        echo = previous_output.strip()[:MAX_REPAIR_ECHO_CHARS] or "(resposta vazia)"
        instruction = render_template(REPAIR_FILE, self._registry.read(version, REPAIR_FILE), {"error": error})
        return [*messages, {"role": "assistant", "content": echo}, {"role": "user", "content": instruction.strip()}]
