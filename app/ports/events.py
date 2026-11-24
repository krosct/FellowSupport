"""Porta do log de eventos (ADR 0043): o que o núcleo registra para observabilidade, sem saber onde vai parar.

Os serviços emitem um evento por geração, por lote do modo ``all``, por avaliação e por comparação. Quem decide o
formato e o destino (hoje, um arquivo JSON Lines na raiz) é o adaptador ligado no ``container``.
"""

from collections.abc import Mapping
from typing import Protocol

# Nomes dos eventos, definidos uma única vez (SSOT): serviços, adaptador e testes leem daqui.
EVENT_GENERATION = "generation"
EVENT_GENERATION_BATCH = "generation_batch"
EVENT_EVALUATION = "evaluation"
EVENT_COMPARISON = "comparison"


class EventLog(Protocol):
    """Destino dos eventos de observabilidade.

    ``emit`` nunca deve derrubar o caso de uso: uma falha ao registrar é problema do log, não da geração.
    """

    def emit(self, event: str, fields: Mapping[str, object]) -> None:
        """Registra o evento ``event`` com os campos ``fields`` (valores serializáveis em JSON)."""
        ...


class NullEventLog:
    """Log que descarta tudo: padrão dos contextos montados sem ``container`` (testes de unidade)."""

    def emit(self, event: str, fields: Mapping[str, object]) -> None:
        """Não faz nada."""


NULL_EVENT_LOG = NullEventLog()
