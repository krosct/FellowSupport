"""Limite de taxa por IP, em memória, para os endpoints que chamam o LLM (ADR 0024 e 0033).

Num deploy público, qualquer visitante pode disparar gerações e consumir a cota gratuita do provedor. Este adaptador
de entrada recusa com 429 (Too Many Requests) o IP que passa de ``RATE_LIMIT_PER_MIN`` chamadas dentro de uma
janela deslizante de 60 s. Fica no servidor, e só nele, porque todos os clientes (o site e a CLI) passam pela API:
o mesmo limite vale para todos. "Quem é o cliente" (o IP) é um conceito de HTTP, por isso não mora no domínio.

Decisões:

- **Janela deslizante** (guarda o instante de cada chamada): não permite a rajada de 2x o limite na virada de minuto
  que uma janela fixa permitiria.
- **Em memória**: simples e sem dependência, mas por processo; por isso o deploy roda com ``--workers 1`` e o
  contador zera a cada reinício do serviço.
- **IP vem de ``request.client``**: com ``uvicorn --proxy-headers --forwarded-allow-ips 127.0.0.1``, o uvicorn
  troca o IP do par pelo do ``X-Forwarded-For`` **somente** quando a conexão vem do proxy local. Uma conexão direta
  de outro endereço não consegue falsificar o IP com esse cabeçalho. Sem proxy reverso, ``request.client`` já é o IP
  real.
- **Só a rota que chama o LLM** (``/api/generate``) usa a dependência
  ``limit_llm_calls``; leituras (catálogo, histórico, ``/healthz``) e o salvamento da comparação nunca são
  limitados. Cada requisição conta uma vez, inclusive as que acertam o cache (a rota não sabe de antemão se haverá
  chamada ao modelo), as recusadas com 409 por pedir confirmação de substituição do cache (ADR 0036) e o modo
  ``all`` (quatro chamadas ao modelo, mas uma requisição).
- **0 desliga** o limite (útil em ambiente local e nos testes).
"""

import math
import threading
import time
from collections import deque
from collections.abc import Callable

from fastapi import Depends, HTTPException, Request

# Janela do limite: ``RATE_LIMIT_PER_MIN`` é o número de chamadas por esta janela, em segundos.
RATE_LIMIT_WINDOW_S = 60.0

# Teto de IPs acompanhados ao mesmo tempo: limita a memória sob um fluxo de IPs distintos (por exemplo, IPv6).
MAX_TRACKED_IPS = 10_000

# Mensagem única do 429 por IP (curta, em pt-BR). ``{seconds}`` é o tempo até a próxima chamada ser aceita.
RATE_LIMIT_IP_MESSAGE = "Muitas requisições deste endereço; tente de novo em {seconds} s."

# Chave usada quando a conexão não informa o cliente (não acontece sob o uvicorn; só em transportes de teste).
UNKNOWN_CLIENT = "unknown"


class SlidingWindowLimiter:
    """Contador de janela deslizante por chave, seguro para threads (os endpoints rodam no threadpool)."""

    def __init__(
        self,
        limit: int,
        window_s: float = RATE_LIMIT_WINDOW_S,
        clock: Callable[[], float] = time.monotonic,
        max_keys: int = MAX_TRACKED_IPS,
    ) -> None:
        """``limit`` é o máximo de chamadas por ``window_s`` (0 desliga). ``clock`` é injetável para os testes."""
        self._limit = limit
        self._window_s = window_s
        self._clock = clock
        self._max_keys = max_keys
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        """Verdadeiro quando o limite está ligado (``limit`` maior que zero)."""
        return self._limit > 0

    def acquire(self, key: str) -> float | None:
        """Registra uma chamada de ``key``. Devolve ``None`` se foi aceita ou os segundos a esperar se foi recusada.

        Uma chamada recusada não entra na janela: insistir não prolonga o bloqueio.
        """
        # Descarta registros vencidos da janela, checa o teto e registra nova chamada.
        if not self.enabled:
            return None
        now = self._clock()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= now - self._window_s:
                hits.popleft()
            if len(hits) >= self._limit:
                return hits[0] + self._window_s - now
            hits.append(now)
            self._trim(now)
            return None

    def _trim(self, now: float) -> None:
        """Mantém o dicionário abaixo de ``max_keys``: descarta as chaves vencidas e, se preciso, as mais antigas."""
        # Remove IPs vencidos e, se ainda exceder o teto, descarta os mais antigos.
        if len(self._hits) <= self._max_keys:
            return
        expired = [key for key, hits in self._hits.items() if not hits or hits[-1] <= now - self._window_s]
        for key in expired:
            del self._hits[key]
        while len(self._hits) > self._max_keys:
            del self._hits[next(iter(self._hits))]


def client_ip(request: Request) -> str:
    """IP do cliente já resolvido pelo servidor (o uvicorn aplica o ``X-Forwarded-For`` só do proxy confiável)."""
    return request.client.host if request.client else UNKNOWN_CLIENT


def limit_llm_calls(request: Request) -> None:
    """Dependência das rotas que chamam o LLM: responde 429 com ``Retry-After`` quando o IP passa do limite."""
    # Consulta o limitador para o IP e responde 429 com Retry-After se bloqueado.
    wait = request.app.state.rate_limiter.acquire(client_ip(request))
    if wait is None:
        return
    seconds = max(1, math.ceil(wait))
    raise HTTPException(
        status_code=429,
        detail=RATE_LIMIT_IP_MESSAGE.format(seconds=seconds),
        headers={"Retry-After": str(seconds)},
    )


# Usada em ``routers.py``: ``@api_router.post(..., dependencies=LLM_CALL_LIMIT)``.
LLM_CALL_LIMIT = [Depends(limit_llm_calls)]
