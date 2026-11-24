"""Testes dos endpoints via TestClient (sem rede)."""

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.adapters.api.main import create_app
from app.config import Settings
from app.container import build_container
from app.domain import rubric
from tests.support import LATEST_VERSION

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


def test_meta_traz_enums_tipos_rubrica_e_versao(client: TestClient) -> None:
    # Garante que /api/meta publica enums, tipos e rubrica esperados pelo front.
    meta = client.get("/api/meta").json()
    assert [o["value"] for o in meta["enums"]["tech_level"]] == ["leigo", "intermediário", "avançado"]
    assert [o["value"] for o in meta["enums"]["comm_style"]] == ["direto", "detalhado", "didático"]
    assert [o["value"] for o in meta["enums"]["channel"]] == ["chat", "e-mail", "telefone"]
    assert [o["value"] for o in meta["content_types"]] == [
        "diagnosis", "resolution_steps", "clarifying_questions", "flow_summary",
    ]
    assert meta["all_option"] == {"value": "all", "label": "Todos"}
    assert [c["key"] for c in meta["rubric"]["criteria"]] == list(rubric.CRITERIA_KEYS)
    assert meta["rubric"]["scale"]["min"] == 1 and meta["rubric"]["scale"]["max"] == 5
    assert meta["default_prompt_version"] == LATEST_VERSION
    assert meta["llm"]["provider"] == "fake"


def test_meta_nunca_expoe_segredo(settings: Settings) -> None:
    com_chave = Settings(
        catalog_dir=settings.catalog_dir, openrouter_api_key=SecretStr(SEGREDO), llm_provider="openrouter"
    )
    client = TestClient(create_app(build_container(com_chave), frontend_dist=None))
    corpo = client.get("/api/meta").text
    assert SEGREDO not in corpo
    assert "api_key" not in corpo.lower()
    assert "base_url" not in corpo.lower()


def test_erro_de_dominio_vira_http(settings: Settings, tmp_path) -> None:
    """Catálogo malformado (ValidationFailed) responde 422 com mensagem, não 500."""
    (tmp_path / "profiles.json").write_text("{nao e json", encoding="utf-8")
    quebrado = Settings(catalog_dir=tmp_path)
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


def test_admin_api_key_protege_cliente_ticket_e_prompt_e_libera_gerar_e_historico(settings: Settings) -> None:
    protegida = settings.model_copy(update={"admin_api_key": SecretStr("segredo-admin")})
    client = TestClient(create_app(build_container(protegida), frontend_dist=None))

    meta = client.get("/api/meta").json()
    assert meta["admin_protected"] is True and "segredo-admin" not in str(meta)

    perfil_body = {"name": "Ana", "tech_level": "leigo", "comm_style": "direto", "channel": "chat"}
    # Sem chave ou com chave errada: cliente, ticket e prompt retornam 401.
    for method, path, body in (
        ("POST", "/api/profiles", perfil_body),
        ("PUT", "/api/profiles/marta", perfil_body),
        ("DELETE", "/api/profiles/marta", None),
        ("POST", "/api/tickets", {"title": "T", "text": "Corpo"}),
        ("PUT", "/api/tickets/t-2fa", {"title": "T", "text": "Corpo"}),
        ("DELETE", "/api/tickets/t-2fa", None),
        ("POST", "/api/prompts", {"based_on": "v1", "description": "x", "changes": [], "files": {}}),
        ("DELETE", "/api/prompts/v2", None),
    ):
        kwargs = {"json": body} if body is not None else {}
        assert client.request(method, path, **kwargs).status_code == 401
        assert client.request(method, path, headers={"X-Admin-Key": "errada"}, **kwargs).status_code == 401

    # Com X-Admin-Key válida: operações administrativas funcionam.
    ok_headers = {"X-Admin-Key": "segredo-admin"}
    criado_p = client.post(
        "/api/profiles",
        headers=ok_headers,
        json={"name": "Ana", "tech_level": "leigo", "comm_style": "direto", "channel": "chat"},
    )
    assert criado_p.status_code == 201
    assert client.delete(f"/api/profiles/{criado_p.json()['id']}", headers=ok_headers).status_code == 200

    # Gerar e histórico continuam abertos para todos sem X-Admin-Key.
    gen = client.post("/api/generate", json={"profile_id": "marta", "ticket_id": "t-2fa"})
    assert gen.status_code == 200
    assert client.get("/api/runs").status_code == 200


def test_deploy_mode_exige_openrouter_key_da_sessao_e_admin_configurada(settings: Settings, monkeypatch) -> None:
    # Em deploy (PUBLIC_URL preenchida): chave do servidor não é usada automaticamente na geração.
    deploy_sem_admin = settings.model_copy(
        update={
            "llm_provider": "openrouter",
            "openrouter_api_key": SecretStr(SEGREDO),
            "public_url": "https://app.exemplo.com",
        }
    )
    c1 = TestClient(create_app(build_container(deploy_sem_admin), frontend_dist=None))
    meta = c1.get("/api/meta").json()
    assert meta["deploy_mode"] is True and meta["llm"]["server_key_configured"] is False
    assert meta["admin_protected"] is True

    # Sem ADMIN_API_KEY configurada no servidor em deploy, mutações são recusadas (403).
    assert c1.post("/api/tickets", json={"title": "T", "text": "Corpo"}).status_code == 403

    # Sem X-OpenRouter-Key da sessão, geração não usa a chave do .env em deploy (503).
    r_sem_key = c1.post("/api/generate", json={"profile_id": "marta", "ticket_id": "t-2fa"})
    assert r_sem_key.status_code == 503 and "openrouter_api_key" in r_sem_key.json()["detail"]

    # Com X-OpenRouter-Key no cabeçalho da sessão, a chamada usa a chave informada pelo usuário.
    usadas: list[str] = []

    class FakeClient:
        def complete(self, messages, schema, params):
            from app.adapters.llm.fake import FakeLLM

            return FakeLLM().complete(messages, schema, params)

    def fake_build(s, *, api_key_override=None):
        usadas.append(api_key_override or "")
        if not (api_key_override or "").strip():
            from app.adapters.llm.factory import MissingKeyLLM

            return MissingKeyLLM("faltou chave")
        return FakeClient()

    monkeypatch.setattr("app.adapters.api.routers.build_llm_client", fake_build)
    r_com_key = c1.post(
        "/api/generate",
        headers={"X-OpenRouter-Key": "sk-sessao-usuario"},
        json={"profile_id": "marta", "ticket_id": "t-2fa"},
    )
    assert r_com_key.status_code == 200
    assert usadas == ["sk-sessao-usuario"]
