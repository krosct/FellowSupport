"""DTOs (formatos de resposta) da API HTTP.

Mantêm o contrato público separado dos modelos internos do domínio. Perfis e tickets reaproveitam os próprios
modelos do domínio; só ``/api/meta`` precisa de um formato dedicado.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.domain.models import ContentType, RunRecord
from app.domain.prompting.registry import PromptVersion


class OptionOut(BaseModel):
    """Um valor de enum com o rótulo exibido na interface."""

    value: str
    label: str


class EnumsOut(BaseModel):
    """Enums do perfil de cliente (item 4.1 do PDF)."""

    tech_level: list[OptionOut]
    comm_style: list[OptionOut]
    channel: list[OptionOut]


class CriterionOut(BaseModel):
    """Critério da rubrica."""

    key: str
    label: str
    description: str


class ScaleOut(BaseModel):
    """Escala de notas da rubrica."""

    min: int
    max: int
    labels: dict[str, str]


class RubricOut(BaseModel):
    """Rubrica completa."""

    criteria: list[CriterionOut]
    scale: ScaleOut


class LimitsOut(BaseModel):
    """Limites que a interface precisa conhecer."""

    max_ticket_chars: int


class LlmInfoOut(BaseModel):
    """Informações públicas do provedor. Nunca inclui chave nem URL."""

    provider: str
    model: str


class MetaOut(BaseModel):
    """Constantes do domínio servidas ao front-end (ADR 0014)."""

    enums: EnumsOut
    content_types: list[OptionOut]
    rubric: RubricOut
    confidence_levels: list[OptionOut]
    default_prompt_version: str
    free_ticket_title: str
    limits: LimitsOut
    llm: LlmInfoOut


class PromptVersionOut(PromptVersion):
    """Versão de prompt (conteúdo do ``meta.json``) com a marca de versão padrão."""

    is_default: bool


class GenerateIn(BaseModel):
    """Corpo de ``POST /api/generate``: perfil, ticket (do catálogo **ou** texto livre) e tipo de conteúdo.

    A regra "exatamente um dos dois tickets" é validada no serviço, para API e CLI darem a mesma mensagem.
    """

    profile_id: str
    ticket_id: str | None = None
    ticket_text: str | None = None
    content_type: ContentType = ContentType.DIAGNOSIS
    prompt_version: str | None = None


class GenerateOut(BaseModel):
    """Resposta de ``POST /api/generate``: o registro da execução e o caminho do JSON salvo."""

    saved_path: str
    run: RunRecord
