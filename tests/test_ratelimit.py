"""Testes do limite de taxa por IP (ADR 0033): janela deslizante, rotas limitadas, IP do proxy e valor 0. O limite
mora só na API HTTP e vale para quem chama ``POST /api/generate`` (site e clientes HTTP).

O relógio é injetado (``Relogio``), então nenhum teste espera tempo real; nada chama a rede (ADR 0016).
"""

import threading

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.adapters.api.main import create_app
from app.adapters.api.ratelimit import (
    RATE_LIMIT_IP_MESSAGE,
    RATE_LIMIT_WINDOW_S,
    SlidingWindowLimiter,
)
from app.config import Settings
from app.container import build_container

GERAR = {"profile_id": "marta", "ticket_id": "t-2fa", "content_type": "diagnosis"}


class Relogio:
    """Relógio manual: o teste decide quanto tempo passou."""

    def __init__(self) -> None:
        self.agora = 1000.0

    def __call__(self) -> float:
        return self.agora

    def avancar(self, segundos: float) -> None:
        self.agora += segundos


def _app(settings: Settings, limite: int, relogio: Relogio | None = None):
    limiter = SlidingWindowLimiter(limite, clock=relogio or Relogio())
    return create_app(build_container(settings), frontend_dist=None, rate_limiter=limiter)


# --- Janela deslizante ---


def test_aceita_ate_o_limite_e_recusa_a_proxima_com_o_tempo_de_espera() -> None:
    relogio = Relogio()
    limiter = SlidingWindowLimiter(3, clock=relogio)
    assert [limiter.acquire("1.1.1.1") for _ in range(3)] == [None, None, None]
    relogio.avancar(10)
    assert limiter.acquire("1.1.1.1") == pytest.approx(RATE_LIMIT_WINDOW_S - 10)


def test_a_janela_desliza_a_cada_chamada_e_nao_por_minuto_fechado() -> None:
    relogio = Relogio()
    limiter = SlidingWindowLimiter(2, clock=relogio)
    assert limiter.acquire("ip") is None  # t=0
    relogio.avancar(30)
    assert limiter.acquire("ip") is None  # t=30
    relogio.avancar(29)
    assert limiter.acquire("ip") == pytest.approx(1)  # t=59: a primeira ainda vale por 1 s
    relogio.avancar(1)
    assert limiter.acquire("ip") is None  # t=60: a primeira saiu da janela
    assert limiter.acquire("ip") == pytest.approx(30)  # a de t=30 sai só em t=90


def test_chamada_recusada_nao_prolonga_o_bloqueio() -> None:
    relogio = Relogio()
    limiter = SlidingWindowLimiter(1, clock=relogio)
    assert limiter.acquire("ip") is None
    for _ in range(5):
        relogio.avancar(5)
        assert limiter.acquire("ip") is not None
    relogio.avancar(RATE_LIMIT_WINDOW_S - 25)  # 60 s depois da única chamada aceita
    assert limiter.acquire("ip") is None


def test_cada_ip_tem_a_sua_janela() -> None:
    limiter = SlidingWindowLimiter(1, clock=Relogio())
    assert limiter.acquire("1.1.1.1") is None
    assert limiter.acquire("1.1.1.1") is not None
    assert limiter.acquire("2.2.2.2") is None


def test_limite_zero_desliga() -> None:
    limiter = SlidingWindowLimiter(0, clock=Relogio())
    assert not limiter.enabled
    assert all(limiter.acquire("ip") is None for _ in range(1000))


def test_threads_concorrentes_nunca_passam_do_limite() -> None:
    # Dispara 16 threads concorrentes para validar que o lock mantém o teto exato.
    limiter = SlidingWindowLimiter(25, clock=Relogio())
    aceitas: list[bool] = []
    trava = threading.Lock()

    def chamar() -> None:
        for _ in range(10):
            ok = limiter.acquire("ip") is None
            with trava:
                aceitas.append(ok)

    threads = [threading.Thread(target=chamar) for _ in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(aceitas) == 160 and sum(aceitas) == 25


def test_o_numero_de_ips_acompanhados_tem_teto() -> None:
    relogio = Relogio()
    limiter = SlidingWindowLimiter(1, clock=relogio, max_keys=5)
    for i in range(20):
        limiter.acquire(f"10.0.0.{i}")
    assert len(limiter._hits) <= 5
    # Com o tempo, as chaves vencidas saem antes das ativas.
    relogio.avancar(RATE_LIMIT_WINDOW_S + 1)
    limiter.acquire("10.9.9.9")
    for i in range(5):
        limiter.acquire(f"10.1.1.{i}")
    assert len(limiter._hits) <= 5


# --- Rotas ---


def test_generate_recusa_a_chamada_acima_do_limite_com_429_e_retry_after(settings: Settings) -> None:
    relogio = Relogio()
    cliente = TestClient(_app(settings, 2, relogio))
    assert cliente.post("/api/generate", json=GERAR).status_code == 200
    assert cliente.post("/api/generate", json=GERAR).status_code == 200
    relogio.avancar(15.2)
    r = cliente.post("/api/generate", json=GERAR)
    assert r.status_code == 429
    espera = 45  # 60 - 15,2 arredondado para cima
    assert r.json() == {"detail": RATE_LIMIT_IP_MESSAGE.format(seconds=espera)}
    assert r.headers["retry-after"] == str(espera)
    # Depois da espera indicada, a chamada volta a ser aceita.
    relogio.avancar(espera)
    assert cliente.post("/api/generate", json=GERAR).status_code == 200


def test_recusa_nao_gera_execucao_nem_chama_o_llm(settings: Settings) -> None:
    cliente = TestClient(_app(settings, 1))
    cliente.post("/api/generate", json=GERAR)
    antes = sorted((settings.data_dir / "runs").rglob("*.json"))
    assert cliente.post("/api/generate", json={**GERAR, "use_cache": False}).status_code == 429
    assert sorted((settings.data_dir / "runs").rglob("*.json")) == antes


def test_o_modo_all_conta_como_uma_chamada(settings: Settings) -> None:
    cliente = TestClient(_app(settings, 1))
    assert cliente.post("/api/generate", json={**GERAR, "content_type": "all"}).status_code == 200
    assert cliente.post("/api/generate", json={**GERAR, "content_type": "all"}).status_code == 429


def test_o_limite_e_compartilhado_entre_geracao_simples_e_all(settings: Settings) -> None:
    cliente = TestClient(_app(settings, 2))
    assert cliente.post("/api/generate", json=GERAR).status_code == 200
    assert cliente.post("/api/generate", json={**GERAR, "content_type": "all"}).status_code == 200
    assert cliente.post("/api/generate", json=GERAR).status_code == 429


def test_rotas_de_leitura_e_o_salvamento_da_comparacao_nunca_sao_limitados(settings: Settings) -> None:
    cliente = TestClient(_app(settings, 1))
    cliente.post("/api/generate", json=GERAR)  # esgota o limite
    for caminho in ("/healthz", "/api/meta", "/api/profiles", "/api/tickets", "/api/prompt-versions",
                    "/api/runs", "/api/comparisons"):
        for _ in range(3):
            assert cliente.get(caminho).status_code == 200, caminho
    # Salvar a comparação não chama o LLM: responde 404 (execuções inexistentes), nunca 429.
    corpo = {"run_ids": ["aaaaaaaaaaaa", "bbbbbbbbbbbb"], "evaluations": {}}
    assert cliente.post("/api/comparisons", json=corpo).status_code == 404
    assert cliente.get("/api/runs/inexistente").status_code == 404


def test_limite_zero_nao_limita_as_rotas(settings: Settings) -> None:
    cliente = TestClient(_app(settings, 0))
    assert all(cliente.post("/api/generate", json=GERAR).status_code == 200 for _ in range(15))


def test_o_padrao_do_settings_vem_do_rate_limit_per_min(settings: Settings) -> None:
    """Sem limiter injetado, a fábrica usa ``RATE_LIMIT_PER_MIN`` (10 por padrão; 0 desliga)."""
    cliente = TestClient(create_app(build_container(settings), frontend_dist=None))
    assert [cliente.post("/api/generate", json=GERAR).status_code for _ in range(11)] == [200] * 10 + [429]
    desligado = settings.model_copy(update={"rate_limit_per_min": 0})
    cliente = TestClient(create_app(build_container(desligado), frontend_dist=None))
    assert all(cliente.post("/api/generate", json=GERAR).status_code == 200 for _ in range(12))


def test_rate_limit_negativo_e_recusado_pelo_settings() -> None:
    with pytest.raises(ValidationError):
        Settings(rate_limit_per_min=-1)


# --- IP atrás do proxy (uvicorn --proxy-headers --forwarded-allow-ips 127.0.0.1) ---


def _atras_do_proxy(settings: Settings, par: str, limite: int = 1) -> TestClient:
    """App embrulhado no mesmo middleware que o uvicorn aplica com ``--proxy-headers``; ``par`` é quem conecta."""
    app = ProxyHeadersMiddleware(_app(settings, limite), trusted_hosts="127.0.0.1")  # type: ignore[arg-type]
    return TestClient(app, client=(par, 50000))  # type: ignore[arg-type]


def test_proxy_local_confiavel_separa_os_visitantes_pelo_x_forwarded_for(settings: Settings) -> None:
    cliente = _atras_do_proxy(settings, "127.0.0.1")
    a = {"X-Forwarded-For": "203.0.113.7"}
    b = {"X-Forwarded-For": "203.0.113.8"}
    assert cliente.post("/api/generate", json=GERAR, headers=a).status_code == 200
    assert cliente.post("/api/generate", json=GERAR, headers=a).status_code == 429
    assert cliente.post("/api/generate", json=GERAR, headers=b).status_code == 200


def test_conexao_direta_nao_falsifica_o_ip_com_x_forwarded_for(settings: Settings) -> None:
    """Quem não é o proxy local tem o cabeçalho ignorado: trocar o valor não renova o limite."""
    cliente = _atras_do_proxy(settings, "198.51.100.9")
    assert cliente.post("/api/generate", json=GERAR, headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 200
    assert cliente.post("/api/generate", json=GERAR, headers={"X-Forwarded-For": "2.2.2.2"}).status_code == 429
