"""Testes dos endpoints via TestClient (sem rede)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.adapters.api.main import create_app
from app.config import Settings
from app.container import build_container
from app.domain import rubric

SEGREDO = "sk-or-v1-segredo-de-teste-1234567890"


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(build_container(settings), frontend_dist=None))


def test_healthz(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_profiles(client: TestClient) -> None:
    r = client.get("/api/profiles")
    assert r.status_code == 200
    perfis = r.json()
    assert 3 <= len(perfis) <= 5
    assert {"id", "name", "tech_level", "comm_style", "channel"} <= set(perfis[0])
    assert perfis[0]["id"] == "marta"


def test_tickets(client: TestClient) -> None:
    r = client.get("/api/tickets")
    assert r.status_code == 200
    tickets = r.json()
    assert len(tickets) == 5
    assert all({"id", "title", "text"} <= set(t) for t in tickets)


def test_meta_traz_enums_tipos_rubrica_e_versao(client: TestClient) -> None:
    meta = client.get("/api/meta").json()
    assert [o["value"] for o in meta["enums"]["tech_level"]] == ["leigo", "intermediário", "avançado"]
    assert [o["value"] for o in meta["enums"]["comm_style"]] == ["direto", "detalhado", "didático"]
    assert [o["value"] for o in meta["enums"]["channel"]] == ["chat", "e-mail", "telefone"]
    assert [o["value"] for o in meta["content_types"]] == [
        "diagnosis", "resolution_steps", "clarifying_questions", "flow_summary",
    ]
    assert [c["key"] for c in meta["rubric"]["criteria"]] == list(rubric.CRITERIA_KEYS)
    assert meta["rubric"]["scale"]["min"] == 1 and meta["rubric"]["scale"]["max"] == 5
    assert meta["default_prompt_version"] == "v1"
    assert meta["llm"]["provider"] == "fake"


def test_meta_nunca_expoe_segredo(settings: Settings) -> None:
    com_chave = Settings(
        _env_file=None, catalog_dir=settings.catalog_dir, openrouter_api_key=SEGREDO, llm_provider="openrouter"
    )
    client = TestClient(create_app(build_container(com_chave), frontend_dist=None))
    corpo = client.get("/api/meta").text
    assert SEGREDO not in corpo
    assert "api_key" not in corpo.lower()
    assert "base_url" not in corpo.lower()


def test_erro_de_dominio_vira_http(settings: Settings, tmp_path) -> None:
    """Catálogo malformado (ValidationFailed) responde 422 com mensagem, não 500."""
    (tmp_path / "profiles.json").write_text("{nao e json", encoding="utf-8")
    quebrado = Settings(_env_file=None, catalog_dir=tmp_path)
    client = TestClient(create_app(build_container(quebrado), frontend_dist=None))
    r = client.get("/api/profiles")
    assert r.status_code == 422
    assert "inválido" in r.json()["detail"]


def test_serve_frontend_dist_quando_existe(settings: Settings, tmp_path) -> None:
    (tmp_path / "index.html").write_text("<html><body>FellowSupport UI</body></html>", encoding="utf-8")
    client = TestClient(create_app(build_container(settings), frontend_dist=tmp_path))
    assert "FellowSupport UI" in client.get("/").text
    # As rotas da API continuam com prioridade sobre os estáticos.
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/api/profiles").status_code == 200


def test_sem_frontend_dist_a_raiz_responde_404(client: TestClient) -> None:
    assert client.get("/").status_code == 404
