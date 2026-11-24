"""Rubrica fixa de avaliação: fonte única da verdade (ADR 0020).

Três critérios, notas de 1 a 5 e justificativa escrita. Validação, API (``/api/meta``) e front-end consomem
esta constante; ninguém deve repetir critérios, rótulos ou escala em outro lugar.
"""

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

# Tamanho máximo da justificativa de cada nota (deve ser curta). Vale para a avaliação do
# candidato, e o formulário do site o recebe por ``/api/meta``.
JUSTIFICATION_MAX_CHARS = 500

# Rótulos da escala de notas.
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

# Maior soma possível das notas de uma versão (um ponto máximo por critério). Base do total da comparação.
TOTAL_MAX = len(CRITERIA) * SCORE_MAX


def is_valid_score(score: int) -> bool:
    """Indica se ``score`` é um inteiro dentro da escala da rubrica."""
    return isinstance(score, int) and SCORE_MIN <= score <= SCORE_MAX


def rubric_as_dict() -> dict:
    """Representação serializável da rubrica, usada por ``GET /api/meta``."""
    # Monta o dicionário público com critérios, escala e limites para o /api/meta.
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
        "justification_max_chars": JUSTIFICATION_MAX_CHARS,
        "total_max": TOTAL_MAX,
    }
