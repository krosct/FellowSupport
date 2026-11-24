"""Metadados públicos da aplicação e versões de prompt (SSOT para API, site e CLI).

Centraliza a montagem de enums, tipos de conteúdo, rubrica, limites e versões de prompt para que API e CLI
exponham exatamente as mesmas definições sem duplicação. Não importa ``app.config`` nem ``app.container`` para
preservar a regra hexagonal (``tests/test_architecture.py``).
"""

from pydantic import BaseModel

from app.domain import rubric
from app.domain.comparison import CONCLUSION_MAX_CHARS, MIN_COMPARED_VERSIONS
from app.domain.models import (
    ALL_OPTION_LABEL,
    ALL_OPTION_VALUE,
    PROFILE_NAME_MAX_CHARS,
    TICKET_TITLE_MAX_CHARS,
    Channel,
    CommStyle,
    Confidence,
    ContentType,
    LabeledEnum,
    TechLevel,
)
from app.domain.prompting.registry import (
    BASE_PROMPT_VERSION,
    PROMPT_CHANGE_FIELD_MAX_CHARS,
    PROMPT_DESCRIPTION_MAX_CHARS,
    PROMPT_FILE_MAX_CHARS,
    PromptRegistry,
    PromptVersion,
)
from app.services.comparison import DEFAULT_COMPARISONS_LIMIT
from app.services.history import DEFAULT_HISTORY_LIMIT, PAGE_SIZES


class OptionMeta(BaseModel):
    """Um valor de enum com o rótulo exibido na interface."""

    value: str
    label: str


class EnumsMeta(BaseModel):
    """Enums do perfil de cliente."""

    tech_level: list[OptionMeta]
    comm_style: list[OptionMeta]
    channel: list[OptionMeta]


class CriterionMeta(BaseModel):
    """Critério da rubrica."""

    key: str
    label: str
    description: str


class ScaleMeta(BaseModel):
    """Escala de notas da rubrica."""

    min: int
    max: int
    labels: dict[str, str]


class RubricMeta(BaseModel):
    """Rubrica completa."""

    criteria: list[CriterionMeta]
    scale: ScaleMeta
    justification_max_chars: int
    total_max: int  # maior total possível de uma versão (soma dos critérios)


class LimitsMeta(BaseModel):
    """Limites que as interfaces precisam conhecer."""

    max_ticket_chars: int
    max_ticket_title_chars: int
    max_profile_name_chars: int
    history_limit: int  # limite padrão da listagem do histórico
    comparisons_limit: int  # limite padrão da listagem de comparações
    page_sizes: list[int]  # itens por página oferecidos no histórico e nas comparações
    min_compared_versions: int  # menor número de versões de uma comparação
    conclusion_max_chars: int  # tamanho máximo da conclusão escrita pelo candidato
    base_prompt_version: str  # versão inicial protegida contra remoção
    max_prompt_description_chars: int
    max_prompt_change_chars: int
    max_prompt_file_chars: int


class LlmInfoMeta(BaseModel):
    """Informações públicas do provedor. Nunca inclui chave nem URL."""

    provider: str
    model: str
    server_key_configured: bool = False


class AppMeta(BaseModel):
    """Constantes do domínio e limites da aplicação (ADR 0014)."""

    enums: EnumsMeta
    content_types: list[OptionMeta]
    all_option: OptionMeta
    rubric: RubricMeta
    confidence_levels: list[OptionMeta]
    default_prompt_version: str
    limits: LimitsMeta
    llm: LlmInfoMeta
    admin_protected: bool = False
    deploy_mode: bool = False


class PromptVersionInfo(PromptVersion):
    """Versão de prompt (conteúdo do ``meta.json``) com a marca de versão padrão."""

    is_default: bool


def _options(enum_cls: type[LabeledEnum]) -> list[OptionMeta]:
    """Converte um enum em lista ``{value, label}`` preservando a ordem de declaração."""
    return [OptionMeta(value=item.value, label=item.label) for item in enum_cls]


def build_meta(
    *,
    provider: str,
    model: str,
    max_ticket_chars: int,
    registry: PromptRegistry,
    server_key_configured: bool = False,
    admin_protected: bool = False,
    deploy_mode: bool = False,
) -> AppMeta:
    """Monta os metadados públicos da aplicação a partir do domínio e da configuração recebida."""
    return AppMeta(
        enums=EnumsMeta(
            tech_level=_options(TechLevel), comm_style=_options(CommStyle), channel=_options(Channel)
        ),
        content_types=_options(ContentType),
        all_option=OptionMeta(value=ALL_OPTION_VALUE, label=ALL_OPTION_LABEL),
        confidence_levels=_options(Confidence),
        rubric=RubricMeta.model_validate(rubric.rubric_as_dict()),
        default_prompt_version=registry.latest().version,
        limits=LimitsMeta(
            max_ticket_chars=max_ticket_chars,
            max_ticket_title_chars=TICKET_TITLE_MAX_CHARS,
            max_profile_name_chars=PROFILE_NAME_MAX_CHARS,
            history_limit=DEFAULT_HISTORY_LIMIT,
            comparisons_limit=DEFAULT_COMPARISONS_LIMIT,
            page_sizes=list(PAGE_SIZES),
            min_compared_versions=MIN_COMPARED_VERSIONS,
            conclusion_max_chars=CONCLUSION_MAX_CHARS,
            base_prompt_version=BASE_PROMPT_VERSION,
            max_prompt_description_chars=PROMPT_DESCRIPTION_MAX_CHARS,
            max_prompt_change_chars=PROMPT_CHANGE_FIELD_MAX_CHARS,
            max_prompt_file_chars=PROMPT_FILE_MAX_CHARS,
        ),
        llm=LlmInfoMeta(provider=provider, model=model, server_key_configured=server_key_configured),
        admin_protected=admin_protected,
        deploy_mode=deploy_mode,
    )


def list_prompt_versions(registry: PromptRegistry) -> list[PromptVersionInfo]:
    """Versões de prompt disponíveis, marcando a mais nova como padrão (ADR 0039)."""
    versions = registry.versions()
    default = versions[-1].version if versions else None
    return [PromptVersionInfo(**version.model_dump(), is_default=version.version == default) for version in versions]


__all__ = [
    "AppMeta",
    "CriterionMeta",
    "EnumsMeta",
    "LimitsMeta",
    "LlmInfoMeta",
    "OptionMeta",
    "PromptVersionInfo",
    "RubricMeta",
    "ScaleMeta",
    "build_meta",
    "list_prompt_versions",
]
