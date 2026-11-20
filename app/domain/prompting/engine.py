"""Motor de prompts (ADR 0005): monta as mensagens de chat a partir de perfil, ticket, tipo e versão.

Os textos moram em arquivos versionados (``prompts/<versão>/``) e são preenchidos com ``string.Template``. A
lógica de adaptação ao perfil fica em dados (``adaptation.json``), não dentro dos templates. Montagem:

- mensagem ``system``: ``system.md`` (persona, limites e defesa contra injeção, ADR 0022);
- mensagem ``user``: ``context.md`` (perfil e ticket) seguido do prompt do tipo (ex.: ``diagnosis.md``).
"""

from __future__ import annotations

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
from app.domain.prompting.registry import PromptRegistry
from app.ports.llm import ChatMessage

# Arquivos fixos de cada versão. O prompt de cada tipo de conteúdo é ``<content_type>.md``.
SYSTEM_FILE = "system.md"
CONTEXT_FILE = "context.md"
ADAPTATION_FILE = "adaptation.json"
REPAIR_FILE = "repair.md"

# Dimensões do perfil cobertas por ``adaptation.json``: nome do campo no perfil -> enum com os valores válidos.
ADAPTATION_DIMENSIONS = {"tech_level": TechLevel, "comm_style": CommStyle, "channel": Channel}

# Tags que delimitam o ticket (ADR 0022). Ocorrências delas dentro do texto do cliente são neutralizadas,
# para o relato não "fechar" o bloco e escapar da delimitação.
TICKET_OPEN, TICKET_CLOSE = "<ticket>", "</ticket>"
_TICKET_TAG = re.compile(r"</?\s*ticket\s*>", re.IGNORECASE)

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


def _render(filename: str, template: str, variables: Mapping[str, str]) -> str:
    """Preenche o template. Placeholder sem valor ou ``$`` solto viram ``ValidationFailed`` com o arquivo.

    ``Template.substitute`` faz uma única passada: ``$`` dentro do texto do ticket não é reinterpretado.
    """
    try:
        return Template(template).substitute(variables)
    except KeyError as exc:
        raise ValidationFailed(f"Placeholder sem valor em {filename}: {exc}") from exc
    except ValueError as exc:
        raise ValidationFailed(f"Placeholder inválido em {filename}: {exc}") from exc


class PromptBuilder:
    """Monta as mensagens de cada geração a partir de uma versão de prompt do registro."""

    def __init__(self, registry: PromptRegistry) -> None:
        self._registry = registry

    def _adaptation(self, version: str) -> dict[str, dict[str, str]]:
        """Lê ``adaptation.json`` e confere que cobre todos os valores de nível, estilo e canal."""
        try:
            data = json.loads(self._registry.read(version, ADAPTATION_FILE))
        except json.JSONDecodeError as exc:
            raise ValidationFailed(f"JSON inválido em {version}/{ADAPTATION_FILE}: {exc}") from exc
        for dimension, enum_cls in ADAPTATION_DIMENSIONS.items():
            rules = data.get(dimension) if isinstance(data, dict) else None
            missing = [m.value for m in enum_cls if not isinstance(rules, dict) or m.value not in rules]
            if missing:
                raise ValidationFailed(f"{version}/{ADAPTATION_FILE} sem texto para {dimension}: {', '.join(missing)}")
        return data

    def build(
        self, version: str, content_type: ContentType, profile: CustomerProfile, ticket_text: str
    ) -> list[ChatMessage]:
        """Mensagens ``[system, user]`` da geração de ``content_type`` na ``version`` de prompt.

        Variáveis disponíveis nos templates: ``product_name``, ``product_description``, ``customer_name``,
        ``tech_level``, ``comm_style``, ``channel`` (texto de ``adaptation.json`` para o valor do perfil),
        ``channel_format`` (restrição de formato do canal, de ``channel_rules``), ``ticket_text`` e as variáveis
        do tipo (ex.: ``min_hypotheses``, ``min_steps``, ``max_nodes``).
        """
        type_file = type_prompt_file(content_type)
        if not self._registry.has_file(version, type_file):
            raise NotFound(f"A versão {version} não tem prompt para {content_type.value} ({type_file})")

        adaptation = self._adaptation(version)
        variables: dict[str, str] = {
            "product_name": PRODUCT_NAME,
            "product_description": PRODUCT_DESCRIPTION,
            "customer_name": profile.name,
            "ticket_text": _TICKET_TAG.sub("[ticket]", ticket_text).strip(),
            "channel_format": channel_format_instruction(profile.channel),
            **_TYPE_VARIABLES.get(content_type, {}),
        }
        for dimension in ADAPTATION_DIMENSIONS:
            variables[dimension] = adaptation[dimension][getattr(profile, dimension).value]

        system = _render(SYSTEM_FILE, self._registry.read(version, SYSTEM_FILE), variables)
        context = _render(CONTEXT_FILE, self._registry.read(version, CONTEXT_FILE), variables)
        task = _render(type_file, self._registry.read(version, type_file), variables)
        return [
            {"role": "system", "content": system.strip()},
            {"role": "user", "content": f"{context.strip()}\n\n{task.strip()}"},
        ]

    def build_repair(
        self, version: str, messages: Sequence[ChatMessage], previous_output: str, error: str
    ) -> list[ChatMessage]:
        """Mensagens da tentativa de reparo (ADR 0004): o pedido original, a resposta inválida e o erro.

        A resposta anterior entra como mensagem do ``assistant`` (truncada) e o erro de validação, sem eco dos
        valores, vai no ``repair.md``.
        """
        echo = previous_output.strip()[:MAX_REPAIR_ECHO_CHARS] or "(resposta vazia)"
        instruction = _render(REPAIR_FILE, self._registry.read(version, REPAIR_FILE), {"error": error})
        return [*messages, {"role": "assistant", "content": echo}, {"role": "user", "content": instruction.strip()}]
