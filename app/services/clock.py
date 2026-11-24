"""Relógio dos serviços: um só ponto para obter "agora" no fuso configurado.

Os serviços recebem o relógio como dependência (``clock``) e usam este como padrão; os testes injetam um relógio
fixo para ter carimbos previsíveis.
"""

from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

# Contrato do relógio: recebe o fuso e devolve o instante atual nele.
Clock = Callable[[ZoneInfo], datetime]


def system_clock(tz: ZoneInfo) -> datetime:
    """Relógio real no fuso pedido."""
    return datetime.now(tz)


def now_iso(clock: Clock, timezone: str) -> str:
    """Instante atual em ISO 8601 com o fuso ``timezone`` (``2026-11-20T14:03:11-03:00``), como nos registros."""
    # Formata a data atual no fuso pedido sem incluir microssegundos.
    return clock(ZoneInfo(timezone)).isoformat(timespec="seconds")
