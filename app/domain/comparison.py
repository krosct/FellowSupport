"""Comparação de versões de prompt (ADR 0021 e 0031): regras puras, sem I/O.

Três responsabilidades, todas testáveis sem disco nem LLM:

- **Justiça** (``find_unfairness``): só a versão do prompt pode diferir entre as execuções comparadas; perfil, ticket,
  tipo, provedor, modelo (pedido e efetivo) e parâmetros precisam ser iguais. Devolve o que difere, em pt-BR.
- **Vencedor** (``decide_winner``): maior soma das notas do candidato; empate no topo não tem vencedor.
- **Registro** (``ComparisonRecord``): o arquivo ``var/comparisons/<id>.json``, com cenário, execuções, avaliações
  por versão, total por versão, vencedor e conclusão.
"""

from collections.abc import Callable, Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.domain import rubric
from app.domain.cache_key import normalize_ticket
from app.domain.errors import ValidationFailed
from app.domain.evaluation import require_evaluable
from app.domain.models import ContentType, CustomerProfile, RunParams, RunRecord, RunTicket

COMPARISON_SCHEMA_VERSION = 1

# Tamanho do id e formato aceito (mesmo critério do id de execução: hexadecimal, sem curingas nem ``..``).
COMPARISON_ID_LENGTH = 12
COMPARISON_ID_PATTERN = rf"[0-9a-f]{{{COMPARISON_ID_LENGTH}}}"

# Mínimo de versões para haver comparação, e tamanho máximo da conclusão escrita pelo autor.
MIN_COMPARED_VERSIONS = 2
CONCLUSION_MAX_CHARS = 1000

# Quem escreveu a conclusão: o candidato (texto livre) ou o sistema (resumo dos totais, quando o candidato não escreve).
CONCLUSION_BY_CANDIDATE = "candidato"
CONCLUSION_BY_SYSTEM = "automática"

# --- Justiça ---------------------------------------------------------------------------------------------


def _short(text: str, size: int = 40) -> str:
    """Trecho curto de um texto para a mensagem de erro."""
    text = " ".join(text.split())
    return text if len(text) <= size else text[:size].rstrip() + "..."


# Campos que precisam ser iguais: (rótulo em pt-BR, valor comparado, texto exibido quando difere).
# ``valor comparado`` é o que decide a igualdade; ``texto exibido`` é só para a mensagem ser legível.
_FairnessField = tuple[str, Callable[[RunRecord], Any], Callable[[RunRecord], str]]
FAIRNESS_FIELDS: tuple[_FairnessField, ...] = (
    ("perfil do cliente", lambda r: r.customer_profile.model_dump(), lambda r: r.customer_profile.id),
    ("ticket", lambda r: normalize_ticket(r.ticket.text), lambda r: r.ticket.id or _short(r.ticket.text)),
    ("tipo de conteúdo", lambda r: r.content_type, lambda r: r.content_type.value),
    ("provedor", lambda r: r.provider, lambda r: r.provider),
    ("modelo configurado", lambda r: r.model, lambda r: r.model),
    ("modelo efetivo", lambda r: r.model_used, lambda r: str(r.model_used)),
    ("temperatura", lambda r: r.params.temperature, lambda r: str(r.params.temperature)),
    ("max_tokens", lambda r: r.params.max_tokens, lambda r: str(r.params.max_tokens)),
    ("modo estruturado", lambda r: r.params.structured_mode, lambda r: r.params.structured_mode),
    ("raciocínio", lambda r: r.params.reasoning, lambda r: r.params.reasoning),
)


def find_unfairness(runs: Sequence[RunRecord]) -> list[str]:
    """O que difere entre as execuções além da versão do prompt, uma frase por campo (lista vazia = justa).

    Compara todas com a primeira. O ``model_used`` é o modelo que de fato respondeu (um acerto de cache herda o da
    origem), então duas execuções com o mesmo modelo pedido, mas respondidas por modelos diferentes, são recusadas.
    """
    # Verifica cada campo obrigatório e lista os que divergem entre as execuções.
    problems = []
    for label, value, shown in FAIRNESS_FIELDS:
        if len({repr(value(run)) for run in runs}) > 1:
            detail = ", ".join(f"{run.prompt_version}: {shown(run)}" for run in runs)
            problems.append(f"{label} ({detail})")
    return problems


# --- Vencedor e conclusão --------------------------------------------------------------------------------


def check_distinct(values: Sequence[str], what: str) -> None:
    """Exige 2 ou mais itens distintos (execuções ou versões): comparar algo com ele mesmo não mede nada."""
    if len(values) < MIN_COMPARED_VERSIONS:
        raise ValidationFailed(f"Escolha ao menos {MIN_COMPARED_VERSIONS} {what} para comparar.")
    if len(set(values)) != len(values):
        raise ValidationFailed(f"As {what} comparadas devem ser diferentes entre si.")


def assert_fair(records: Sequence[RunRecord]) -> None:
    """Levanta ``ValidationFailed`` dizendo o que difere entre as execuções (ADR 0021); só a versão pode diferir."""
    problems = find_unfairness(records)
    if problems:
        raise ValidationFailed(
            "Comparação injusta: as execuções diferem em " + "; ".join(problems)
            + ". Só a versão do prompt pode mudar."
        )


def check_comparable(records: Sequence[RunRecord]) -> None:
    """Confere que as execuções podem ser comparadas; ``ValidationFailed`` com o motivo se não puderem.

    Exige execuções distintas (2 ou mais), com saída, geradas de fato (um acerto de cache repete a saída da origem:
    compara-se a origem), de versões diferentes e do mesmo cenário (ADR 0021). A API confere ao salvar; a CLI confere
    antes de perguntar as notas, com as execuções que leu da API.
    """
    check_distinct([record.run_id for record in records], "execuções")
    for record in records:
        require_evaluable(record)
        if record.cache_hit:
            raise ValidationFailed(
                f"A execução {record.run_id} veio do cache: compare a execução de origem ({record.source_run_id})."
            )
    check_distinct([record.prompt_version for record in records], "versões")
    assert_fair(records)


def version_sort_key(version: str) -> int:
    """Chave de ordenação numérica de ``v1``, ``v2``, ``v10``... (``v2`` antes de ``v10``)."""
    return int(version.lstrip("v"))


def decide_winner(totals: Mapping[str, int]) -> str | None:
    """Versão com a maior soma de notas, ou ``None`` quando há empate no topo.

    Não há critério de desempate: escolher um (por exemplo, "o de maior clareza") esconderia um empate que também é
    resultado. A conclusão do candidato pode explicar a preferência.
    """
    # Encontra a maior soma e só devolve vencedor se não houver empate no topo.
    best = max(totals.values())
    leaders = [version for version, total in totals.items() if total == best]
    return leaders[0] if len(leaders) == 1 else None


def auto_conclusion(totals: Mapping[str, int], winner: str | None) -> str:
    """Resumo dos totais, usado quando o candidato não escreve a conclusão."""
    # Formata o placar final indicando quem venceu ou se houve empate.
    placar = ", ".join(f"{version}: {total}" for version, total in totals.items())
    if winner is None:
        return f"Empate no total das notas do candidato ({placar}; máximo {rubric.TOTAL_MAX})."
    return f"A versão {winner} venceu pelo total das notas do candidato ({placar}; máximo {rubric.TOTAL_MAX})."


# --- Registro --------------------------------------------------------------------------------------------


class ComparisonScenario(BaseModel):
    """O cenário comum às execuções: tudo o que a justiça exige que seja igual."""

    customer_id: str
    customer_profile: CustomerProfile
    ticket: RunTicket
    content_type: ContentType
    provider: str
    model: str
    model_used: str | None = None
    params: RunParams


class ComparisonVersion(BaseModel):
    """Uma versão comparada: a execução, a saída (cópia, para o arquivo ser autossuficiente) e a avaliação.

    ``evaluation`` é a nota do candidato, cuja soma compõe o ``total``.
    """

    prompt_version: str
    run_id: str
    run_path: str  # onde está o JSON da execução
    prompt_sha256: str
    cache_hit: bool
    output: dict | None = None
    rendered: str | None = None
    evaluation: dict
    total: int = Field(description=f"Soma das notas do candidato (de {len(rubric.CRITERIA)} a {rubric.TOTAL_MAX}).")


class ComparisonRecord(BaseModel):
    """Uma comparação salva em ``var/comparisons/<id>.json`` (ADR 0031).

    ``winner`` é a versão vencedora ou ``None`` em caso de empate. ``conclusion_source`` diz se o texto da conclusão
    é do candidato ou o resumo automático dos totais.
    """

    schema_version: int = COMPARISON_SCHEMA_VERSION
    comparison_id: str
    created_at: str  # ISO 8601 com o fuso de APP_TIMEZONE
    scenario: ComparisonScenario
    versions: list[ComparisonVersion]
    winner: str | None
    conclusion: str
    conclusion_source: Literal["candidato", "automática"]


def covers_runs(record: ComparisonRecord, run_ids: Sequence[str]) -> bool:
    """A comparação salva é das mesmas execuções: o mesmo conjunto de ``run_id``, em qualquer ordem (ADR 0038).

    É a identidade usada pelo cache das comparações. Duas comparações do mesmo cenário e versões, mas de execuções
    diferentes, não se equivalem: as saídas avaliadas são outras.
    """
    return {version.run_id for version in record.versions} == set(run_ids)
