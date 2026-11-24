"""DTOs (Data Transfer Object) (formatos de resposta) da API HTTP.

Mantêm o contrato público separado dos modelos internos do domínio. Perfis e tickets reaproveitam os próprios
modelos do domínio; só ``/api/meta`` precisa de um formato dedicado.
"""

from typing import Any

from pydantic import BaseModel, field_validator

from app.domain.comparison import ComparisonRecord
from app.domain.models import (
    ALL_OPTION_VALUE,
    Channel,
    CommStyle,
    ContentType,
    RunRecord,
    TechLevel,
)
from app.services.comparison import ComparisonSummary as ComparisonSummaryOut
from app.services.comparison import ComparisonVersionSummary as ComparisonVersionSummaryOut
from app.services.generators import BatchItemSummary as GenerateItemOut
from app.services.generators import BatchSummary as GenerateAllOut
from app.services.history import RunSummary as RunSummaryOut
from app.services.meta import AppMeta as MetaOut
from app.services.meta import CriterionMeta as CriterionOut
from app.services.meta import EnumsMeta as EnumsOut
from app.services.meta import LimitsMeta as LimitsOut
from app.services.meta import LlmInfoMeta as LlmInfoOut
from app.services.meta import OptionMeta as OptionOut
from app.services.meta import PromptVersionInfo as PromptVersionOut
from app.services.meta import RubricMeta as RubricOut
from app.services.meta import ScaleMeta as ScaleOut
from app.services.prompts import PromptVersionDetail as PromptDetailOut


class TicketIn(BaseModel):
    """Corpo de ``POST /api/tickets`` e ``PUT /api/tickets/{id}``: título e corpo do ticket.

    Os limites e o aparo de espaços são do serviço (``services/catalog``), para API e demais clientes darem a mesma
    mensagem de erro.
    """

    title: str
    text: str


class ProfileIn(BaseModel):
    """Corpo de ``POST /api/profiles`` e ``PUT /api/profiles/{id}``: nome e as três características do cliente.

    Os enums são validados pelo FastAPI (valor desconhecido responde 422); o aparo do nome e o limite são do serviço.
    """

    name: str
    tech_level: TechLevel
    comm_style: CommStyle
    channel: Channel


class PromptChangeIn(BaseModel):
    """Uma mudança informada ao criar ou editar um prompt; aparo e limites ficam em ``services/prompts``."""

    what: str
    why: str
    expected_effect: str


class PromptCreateIn(BaseModel):
    """Corpo de ``POST /api/prompts``: versão base obrigatória, descrição, mudanças e arquivos."""

    based_on: str
    description: str
    changes: list[PromptChangeIn] = []
    files: dict[str, str]


class GenerateIn(BaseModel):
    """Corpo de ``POST /api/generate``: cliente e ticket do catálogo, tipo de conteúdo e versão.

    ``content_type`` aceita os quatro tipos ou ``"all"`` (todos, em paralelo). ``use_cache`` (padrão ``true``) permite
    forçar uma geração nova: com ``false`` o cache não é consultado, mas o resultado é gravado (ADR 0035). Se isso
    substituir uma entrada existente, a API responde 409 com todas as entradas afetadas até o pedido vir com
    ``confirm_replace=true`` (ADR 0036).
    """

    profile_id: str
    ticket_id: str
    content_type: str = ContentType.DIAGNOSIS.value
    prompt_version: str | None = None
    use_cache: bool = True
    confirm_replace: bool = False

    @field_validator("content_type")
    @classmethod
    def _known_type(cls, value: str) -> str:
        """Só os valores de ``ContentType`` e a opção "todos"; o conjunto vem do domínio (SSOT)."""
        # Aceita os quatro tipos do domínio além da opção "all".
        allowed = [*(t.value for t in ContentType), ALL_OPTION_VALUE]
        if value not in allowed:
            raise ValueError(f"content_type deve ser um de: {', '.join(allowed)}")
        return value


class GenerateOut(BaseModel):
    """Resposta de ``POST /api/generate`` para um tipo: o registro da execução e o caminho do JSON salvo."""

    saved_path: str
    run: RunRecord


class RunDetailOut(GenerateOut):
    """Detalhe de uma execução do histórico: mesma forma de ``POST /api/generate`` (``saved_path`` e ``run``),
    para o front reaproveitar o componente que já mostra um resultado."""


class SaveComparisonIn(BaseModel):
    """Corpo de ``POST /api/comparisons``: as execuções comparadas, as notas do candidato por ``run_id`` e a conclusão.

    ``evaluations`` traz as notas de **todas** as execuções (cada comparação é avaliada do zero).
    A validação das notas é do serviço, que responde 422 com a mensagem em pt-BR.
    """

    run_ids: list[str]
    evaluations: dict[str, dict[str, Any]]
    conclusion: str | None = None


class ComparisonOut(BaseModel):
    """Uma comparação salva e o caminho do JSON."""

    saved_path: str
    comparison: ComparisonRecord


__all__ = [
    "ComparisonOut",
    "ComparisonSummaryOut",
    "ComparisonVersionSummaryOut",
    "CriterionOut",
    "EnumsOut",
    "GenerateAllOut",
    "GenerateIn",
    "GenerateItemOut",
    "GenerateOut",
    "LimitsOut",
    "LlmInfoOut",
    "MetaOut",
    "OptionOut",
    "ProfileIn",
    "PromptChangeIn",
    "PromptCreateIn",
    "PromptDetailOut",
    "PromptVersionOut",
    "RubricOut",
    "RunDetailOut",
    "RunSummaryOut",
    "SaveComparisonIn",
    "ScaleOut",
    "TicketIn",
]
