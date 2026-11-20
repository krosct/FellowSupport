"""DTOs (formatos de resposta) da API HTTP.

Mantêm o contrato público separado dos modelos internos do domínio. Perfis e tickets reaproveitam os próprios
modelos do domínio; só ``/api/meta`` precisa de um formato dedicado.
"""

from __future__ import annotations

from pydantic import BaseModel, field_validator

from app.domain.models import ALL_OPTION_VALUE, ContentType, RunError, RunRecord, RunStatus
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
    history_limit: int  # limite padrão da listagem do histórico (``GET /api/runs``)


class LlmInfoOut(BaseModel):
    """Informações públicas do provedor. Nunca inclui chave nem URL."""

    provider: str
    model: str


class MetaOut(BaseModel):
    """Constantes do domínio servidas ao front-end (ADR 0014)."""

    enums: EnumsOut
    content_types: list[OptionOut]
    all_option: OptionOut
    rubric: RubricOut
    confidence_levels: list[OptionOut]
    default_prompt_version: str
    free_ticket_title: str
    limits: LimitsOut
    llm: LlmInfoOut
    cache_enabled: bool  # CACHE_ENABLED: com ``false`` o site desabilita a opção "Usar cache"


class PromptVersionOut(PromptVersion):
    """Versão de prompt (conteúdo do ``meta.json``) com a marca de versão padrão."""

    is_default: bool


class GenerateIn(BaseModel):
    """Corpo de ``POST /api/generate``: perfil, ticket (do catálogo **ou** texto livre) e tipo de conteúdo.

    ``content_type`` aceita os quatro tipos ou ``"all"`` (todos, em paralelo). A regra "exatamente um dos dois
    tickets" é validada no serviço, para API e CLI darem a mesma mensagem. ``use_cache`` (padrão ``true``) permite
    forçar uma geração nova: com ``false`` o cache não é lido nem gravado (ADR 0028).
    """

    profile_id: str
    ticket_id: str | None = None
    ticket_text: str | None = None
    content_type: str = ContentType.DIAGNOSIS.value
    prompt_version: str | None = None
    use_cache: bool = True

    @field_validator("content_type")
    @classmethod
    def _known_type(cls, value: str) -> str:
        """Só os valores de ``ContentType`` e a opção "todos"; o conjunto vem do domínio (SSOT)."""
        allowed = [*(t.value for t in ContentType), ALL_OPTION_VALUE]
        if value not in allowed:
            raise ValueError(f"content_type deve ser um de: {', '.join(allowed)}")
        return value


class GenerateOut(BaseModel):
    """Resposta de ``POST /api/generate`` para um tipo: o registro da execução e o caminho do JSON salvo."""

    saved_path: str
    run: RunRecord


class GenerateItemOut(BaseModel):
    """Um tipo no modo ``all``: com sucesso traz ``run``; com falha, ``error``. ``saved_path`` aponta o JSON da
    execução (que também existe, com ``status: "error"``, quando o erro veio do modelo). Ambos podem faltar só
    se a falha ocorreu antes de existir execução."""

    content_type: ContentType
    saved_path: str | None = None
    run: RunRecord | None = None
    error: RunError | None = None


class GenerateAllOut(BaseModel):
    """Resposta de ``POST /api/generate`` com ``content_type: "all"``: um item por tipo, na ordem de ``ContentType``."""

    results: list[GenerateItemOut]


class RunSummaryOut(BaseModel):
    """Linha da listagem do histórico: o suficiente para a tabela, sem a saída nem as mensagens enviadas.

    O registro completo (``GET /api/runs/{id}``) pode ter dezenas de KB; listar 50 deles inteiros seria pesado.
    """

    run_id: str
    timestamp: str
    status: RunStatus
    customer_id: str
    customer_name: str
    ticket_id: str | None
    ticket_title: str
    content_type: ContentType
    prompt_version: str
    provider: str
    model: str
    model_used: str | None
    cache_key: str | None
    cache_hit: bool
    source_run_id: str | None
    attempts: int
    latency_ms: int
    error: RunError | None
    saved_path: str


class RunDetailOut(GenerateOut):
    """Detalhe de uma execução do histórico: mesma forma de ``POST /api/generate`` (``saved_path`` e ``run``),
    para o front reaproveitar o componente que já mostra um resultado."""
