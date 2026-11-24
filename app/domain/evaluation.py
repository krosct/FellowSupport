"""Avaliação pela rubrica: modelos e regras puras, sem I/O (ADR 0020).

Os critérios vêm de ``rubric.CRITERIA`` (fonte única): o modelo de notas é montado a partir dessa constante, então
acrescentar ou renomear um critério lá muda validação, API, CLI e o JSON de uma vez. A forma do JSON é
um item por critério (``{"clarity": {"score": 4, "justification": "..."}, ...}``) mais os campos de autoria.
"""

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model

from app.domain import rubric
from app.domain.errors import ValidationFailed
from app.domain.models import RunRecord

# Quem assinou a avaliação, gravado no JSON do registro da execução.
EVALUATOR_CANDIDATE = "candidato"


class CriterionScore(BaseModel):
    """Nota de um critério com a justificativa escrita."""

    # A nota é um inteiro de verdade (strict): "4", 4.5 e true são recusados, em vez de arredondados em silêncio.
    # A justificativa é obrigatória e não pode ser só espaços (str_strip_whitespace + min_length).
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    score: int = Field(
        strict=True,
        ge=rubric.SCORE_MIN,
        le=rubric.SCORE_MAX,
        description=f"Nota inteira de {rubric.SCORE_MIN} a {rubric.SCORE_MAX}.",
    )
    justification: str = Field(
        min_length=1,
        max_length=rubric.JUSTIFICATION_MAX_CHARS,
        description="Justificativa curta da nota, em uma ou duas frases.",
    )


# Um campo por critério da rubrica, na ordem dela. ``extra="forbid"`` recusa critérios desconhecidos.
RubricScores = create_model(
    "RubricScores",
    __config__=ConfigDict(extra="forbid"),
    __doc__="Notas e justificativas dos critérios da rubrica (um campo por critério de ``rubric.CRITERIA``).",
    **{criterion.key: (CriterionScore, Field(description=criterion.description)) for criterion in rubric.CRITERIA},  # type: ignore[arg-type]
)


class StoredEvaluation(RubricScores):  # type: ignore[valid-type,misc]
    """Avaliação gravada no registro da execução: as notas mais quem avaliou e quando."""

    evaluator: str
    evaluated_at: str  # ISO 8601 com o fuso de APP_TIMEZONE


def _describe_error(error: Mapping) -> str:
    """Frase em pt-BR para um erro de validação das notas, citando o critério pelo rótulo da rubrica."""
    # Mapeia o código de erro do Pydantic para uma mensagem direta em português.
    loc = tuple(error["loc"])
    labels = {criterion.key: criterion.label for criterion in rubric.CRITERIA}
    where = labels.get(str(loc[0]), str(loc[0])) if loc else "avaliação"
    field = loc[1] if len(loc) > 1 else None
    kind = error["type"]
    if kind == "extra_forbidden":
        return f"critério desconhecido: {error['loc'][-1]}"
    if kind == "missing":
        missing = {"score": "nota", "justification": "justificativa"}.get(str(field), "avaliação")
        return f"{where}: {missing} ausente"
    if field == "score":
        return f"{where}: a nota deve ser um inteiro de {rubric.SCORE_MIN} a {rubric.SCORE_MAX}"
    if field == "justification":
        if kind == "string_too_long":
            return f"{where}: a justificativa passa de {rubric.JUSTIFICATION_MAX_CHARS} caracteres"
        return f"{where}: a justificativa é obrigatória"
    return f"{where}: {error['msg']}"


def describe_score_errors(exc: ValidationError) -> str:
    """Todos os problemas das notas em uma frase só (para toast, CLI e resposta 422)."""
    return "Avaliação inválida: " + "; ".join(_describe_error(error) for error in exc.errors()) + "."


def parse_scores(raw: object) -> BaseModel:
    """Valida as notas recebidas (de formulário, API ou CLI) e devolve o modelo ``RubricScores``.

    Levanta ``ValidationFailed`` com a mensagem em pt-BR: nota fora de 1 a 5 (ou não inteira), justificativa vazia
    ou longa demais, critério faltando ou desconhecido.
    """
    # Exige um mapeamento e valida todas as notas contra o schema da rubrica.
    if not isinstance(raw, Mapping):
        raise ValidationFailed("Avaliação inválida: envie um objeto com um item por critério da rubrica.")
    try:
        return RubricScores.model_validate(raw)
    except ValidationError as exc:
        raise ValidationFailed(describe_score_errors(exc)) from exc


def total_score(evaluation: Mapping) -> int:
    """Soma das notas dos critérios de uma avaliação (``dict`` no formato gravado). Vale de 3 a 15."""
    return sum(int(evaluation[key]["score"]) for key in rubric.CRITERIA_KEYS)


def require_evaluable(record: RunRecord) -> None:
    """Só se avalia uma execução que gerou saída: erro não tem o que ser lido nem nota que o descreva."""
    if record.status != "ok" or record.output is None:
        raise ValidationFailed(f"A execução {record.run_id} terminou em erro e não pode ser avaliada.")
