"""DTOs (formatos de resposta) da API HTTP.

Mantêm o contrato público separado dos modelos internos do domínio. Perfis e tickets reaproveitam os próprios
modelos do domínio; só ``/api/meta`` precisa de um formato dedicado.
"""

from __future__ import annotations

from pydantic import BaseModel


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
    default_prompt_version: str
    limits: LimitsOut
    llm: LlmInfoOut
