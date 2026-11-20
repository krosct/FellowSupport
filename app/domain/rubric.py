"""Rubrica fixa de avaliação do desafio (item 5 do PDF): fonte única da verdade (ADR 0020).

Três critérios, notas de 1 a 5 e justificativa escrita. Validação, API (``/api/meta``) e front-end consomem
esta constante; ninguém deve repetir critérios, rótulos ou escala em outro lugar.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Criterion:
    """Um critério da rubrica: chave estável (usada nos JSONs), rótulo e o que observar."""

    key: str
    label: str
    description: str


# Menor e maior nota possíveis.
SCORE_MIN = 1
SCORE_MAX = 5

# Rótulos da escala sugerida no PDF.
SCORE_LABELS: dict[int, str] = {
    1: "insuficiente",
    2: "fraco",
    3: "adequado",
    4: "bom",
    5: "excelente",
}

# Ordem importa: é a ordem de exibição no formulário e nos JSONs.
CRITERIA: tuple[Criterion, ...] = (
    Criterion(
        key="clarity",
        label="Clareza",
        description="A resposta é compreensível, organizada e evita ambiguidade desnecessária?",
    ),
    Criterion(
        key="customer_fit",
        label="Adequação ao nível do cliente",
        description="Vocabulário, profundidade e explicações combinam com o perfil selecionado?",
    ),
    Criterion(
        key="actionability",
        label="Acionabilidade",
        description="O cliente ou atendente consegue saber o que fazer a seguir?",
    ),
)

CRITERIA_KEYS: tuple[str, ...] = tuple(c.key for c in CRITERIA)


def is_valid_score(score: int) -> bool:
    """Indica se ``score`` é um inteiro dentro da escala da rubrica."""
    return isinstance(score, int) and SCORE_MIN <= score <= SCORE_MAX


def rubric_as_dict() -> dict:
    """Representação serializável da rubrica, usada por ``GET /api/meta``."""
    return {
        "criteria": [
            {"key": c.key, "label": c.label, "description": c.description} for c in CRITERIA
        ],
        "scale": {
            "min": SCORE_MIN,
            "max": SCORE_MAX,
            # Chaves de objeto JSON são sempre texto.
            "labels": {str(score): label for score, label in SCORE_LABELS.items()},
        },
    }
