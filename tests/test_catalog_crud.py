"""Testes do CRUD do catálogo (clientes e tickets): repositórios, serviço e rotas (ADR 0037).

O ``settings`` do conftest aponta para uma cópia do ``catalog/``: nada aqui toca os arquivos reais.
"""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.adapters.api.main import create_app
from app.adapters.storage.json_files import PROFILES_FILE, TICKETS_FILE, JsonProfileRepo, JsonTicketRepo
from app.config import Settings
from app.container import build_container
from app.domain.errors import NotFound, ValidationFailed
from app.domain.models import (
    PROFILE_NAME_MAX_CHARS,
    TICKET_TITLE_MAX_CHARS,
    Channel,
    CommStyle,
    CustomerProfile,
    TechLevel,
    Ticket,
)


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(build_container(settings), frontend_dist=None))


PERFIL = {"name": "Carla", "tech_level": "leigo", "comm_style": "direto", "channel": "chat"}


# --- repositório ------------------------------------------------------------------------------------


def test_tickets_gravam_no_arquivo_do_catalogo_e_nao_em_var(settings: Settings) -> None:
    JsonTicketRepo(settings.catalog_dir).add(Ticket(id="t-novo", title="Novo", text="Corpo"))
    arquivo = settings.catalog_dir / TICKETS_FILE
    assert json.loads(arquivo.read_text(encoding="utf-8"))[-1] == {"id": "t-novo", "title": "Novo", "text": "Corpo"}
    assert not (settings.data_dir / TICKETS_FILE).exists()


def test_perfis_gravam_no_arquivo_do_catalogo_com_acentos(settings: Settings) -> None:
    perfil = CustomerProfile(
        id="c-x", name="João", tech_level=TechLevel.AVANCADO, comm_style=CommStyle.DIDATICO, channel=Channel.EMAIL
    )
    JsonProfileRepo(settings.catalog_dir).add(perfil)
    bruto = (settings.catalog_dir / PROFILES_FILE).read_text(encoding="utf-8")
    assert "João" in bruto and "didático" in bruto
    assert json.loads(bruto)[-1] == {
        "id": "c-x", "name": "João", "tech_level": "avançado", "comm_style": "didático", "channel": "e-mail",
    }


def test_add_update_remove_mantem_ordem_e_persistem_entre_instancias(settings: Settings) -> None:
    loja = JsonTicketRepo(settings.catalog_dir)
    total = len(loja.list_all())
    loja.add(Ticket(id="t-a", title="A", text="a"))
    loja.add(Ticket(id="t-b", title="B", text="b"))
    loja.update(Ticket(id="t-a", title="A2", text="a2"))
    outra = JsonTicketRepo(settings.catalog_dir)
    assert [t.id for t in outra.list_all()][-2:] == ["t-a", "t-b"]
    assert outra.get("t-a").title == "A2"
    assert outra.remove("t-a").id == "t-a"
    assert len(outra.list_all()) == total + 1
    with pytest.raises(NotFound):
        outra.get("t-a")


def test_esvaziar_a_lista_deixa_o_arquivo_vazio(settings: Settings) -> None:
    loja = JsonTicketRepo(settings.catalog_dir)
    for ticket in loja.list_all():
        loja.remove(ticket.id)
    assert JsonTicketRepo(settings.catalog_dir).list_all() == []


def test_id_repetido_limite_e_inexistente_sao_recusados(settings: Settings) -> None:
    loja = JsonTicketRepo(settings.catalog_dir)
    loja.add(Ticket(id="t-a", title="A", text="a"))
    with pytest.raises(ValidationFailed, match="Já existe"):
        loja.add(Ticket(id="t-a", title="A", text="a"))
    loja._max_items = len(loja.list_all())  # instância própria: não afeta as demais
    with pytest.raises(ValidationFailed, match="máximo"):
        loja.add(Ticket(id="t-b", title="B", text="b"))
    with pytest.raises(NotFound):
        loja.update(Ticket(id="t-nada", title="x", text="x"))
    with pytest.raises(NotFound, match="Ticket"):
        loja.remove("t-nada")


def test_adicoes_concorrentes_nao_perdem_itens(settings: Settings) -> None:
    loja = JsonTicketRepo(settings.catalog_dir)
    loja._max_items = 1000
    base = len(loja.list_all())
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i: loja.add(Ticket(id=f"t-c{i}", title="c", text="c")), range(40)))
    assert len(JsonTicketRepo(settings.catalog_dir).list_all()) == base + 40


# --- rotas de tickets -------------------------------------------------------------------------------


def test_post_ticket_cria_com_id_gerado_e_aparece_na_lista(client: TestClient) -> None:
    antes = client.get("/api/tickets").json()
    r = client.post("/api/tickets", json={"title": "  Impressora travada  ", "text": "  Não imprime.  "})
    assert r.status_code == 201
    criado = r.json()
    assert criado["id"].startswith("t-") and len(criado["id"]) == 10
    assert (criado["title"], criado["text"]) == ("Impressora travada", "Não imprime.")
    depois = client.get("/api/tickets").json()
    assert len(depois) == len(antes) + 1 and depois[-1] == criado


def test_put_ticket_edita_sem_mudar_id_nem_posicao(client: TestClient) -> None:
    ids = [t["id"] for t in client.get("/api/tickets").json()]
    alvo = ids[-1]
    r = client.put(f"/api/tickets/{alvo}", json={"title": "Novo título", "text": "Novo corpo"})
    assert r.status_code == 200
    assert r.json() == {"id": alvo, "title": "Novo título", "text": "Novo corpo"}
    assert [t["id"] for t in client.get("/api/tickets").json()] == ids


def test_delete_ticket_remove_e_devolve(client: TestClient) -> None:
    alvo = client.get("/api/tickets").json()[-1]["id"]
    r = client.delete(f"/api/tickets/{alvo}")
    assert r.status_code == 200 and r.json()["id"] == alvo
    assert alvo not in [t["id"] for t in client.get("/api/tickets").json()]
    assert client.delete(f"/api/tickets/{alvo}").status_code == 404
    assert client.put(f"/api/tickets/{alvo}", json={"title": "a", "text": "b"}).status_code == 404


@pytest.mark.parametrize(
    ("corpo", "trecho"),
    [
        ({"title": "   ", "text": "x"}, "título"),
        ({"title": "x", "text": "   "}, "corpo"),
        ({"title": "x" * (TICKET_TITLE_MAX_CHARS + 1), "text": "x"}, "passa do limite"),
        ({"title": "x", "text": "x" * 4001}, "passa do limite"),
    ],
)
def test_post_ticket_recusa_entrada_invalida_com_422(client: TestClient, corpo: dict, trecho: str) -> None:
    r = client.post("/api/tickets", json=corpo)
    assert r.status_code == 422 and trecho in r.json()["detail"]
    assert client.post("/api/tickets", json={"title": "x"}).status_code == 422


# --- rotas de clientes ------------------------------------------------------------------------------


def test_crud_de_cliente_pelas_rotas(client: TestClient) -> None:
    antes = client.get("/api/profiles").json()
    r = client.post("/api/profiles", json={**PERFIL, "name": "  Carla  "})
    assert r.status_code == 201
    criado = r.json()
    assert criado["id"].startswith("c-") and criado["name"] == "Carla" and criado["channel"] == "chat"
    assert client.get("/api/profiles").json() == [*antes, criado]

    editado = client.put(f"/api/profiles/{criado['id']}", json={**PERFIL, "name": "Carla M.", "tech_level": "avançado"})
    assert editado.status_code == 200
    assert editado.json() == {**criado, "name": "Carla M.", "tech_level": "avançado"}

    assert client.delete(f"/api/profiles/{criado['id']}").json()["id"] == criado["id"]
    assert client.get("/api/profiles").json() == antes
    assert client.delete(f"/api/profiles/{criado['id']}").status_code == 404
    assert client.put(f"/api/profiles/{criado['id']}", json=PERFIL).status_code == 404


@pytest.mark.parametrize(
    "corpo",
    [
        {**PERFIL, "name": "   "},
        {**PERFIL, "name": "x" * (PROFILE_NAME_MAX_CHARS + 1)},
        {**PERFIL, "tech_level": "mestre"},
        {**PERFIL, "channel": "pombo"},
        {"name": "só nome"},
    ],
)
def test_post_cliente_recusa_entrada_invalida_com_422(client: TestClient, corpo: dict) -> None:
    assert client.post("/api/profiles", json=corpo).status_code == 422


# --- integração com a geração e o histórico ---------------------------------------------------------


def test_cliente_e_ticket_criados_geram_e_o_historico_sobrevive_a_remocao(client: TestClient) -> None:
    ticket = client.post("/api/tickets", json={"title": "Meu ticket", "text": "Relato do meu problema."}).json()
    perfil = client.post("/api/profiles", json=PERFIL).json()
    g = client.post("/api/generate", json={"profile_id": perfil["id"], "ticket_id": ticket["id"]})
    assert g.status_code == 200
    client.delete(f"/api/tickets/{ticket['id']}")
    client.delete(f"/api/profiles/{perfil['id']}")
    run = client.get(f"/api/runs/{g.json()['run']['run_id']}").json()["run"]
    assert run["ticket"] == {"id": ticket["id"], "title": "Meu ticket", "text": "Relato do meu problema."}
    assert run["customer_profile"]["name"] == "Carla"
    # Com os ids removidos, gerar de novo responde 404 e nada é gerado.
    assert client.post("/api/generate", json={"profile_id": perfil["id"], "ticket_id": "t-2fa"}).status_code == 404
    assert client.post("/api/generate", json={"profile_id": "marta", "ticket_id": ticket["id"]}).status_code == 404


def test_meta_traz_os_limites_e_nao_traz_o_titulo_do_ticket_livre(client: TestClient) -> None:
    meta = client.get("/api/meta").json()
    assert meta["limits"]["max_ticket_title_chars"] == TICKET_TITLE_MAX_CHARS
    assert meta["limits"]["max_profile_name_chars"] == PROFILE_NAME_MAX_CHARS
    assert "free_ticket_title" not in meta


def test_as_rotas_alteram_so_a_copia_de_teste_do_catalogo(client: TestClient, settings: Settings) -> None:
    real = Path(__file__).resolve().parent.parent / "catalog" / TICKETS_FILE
    antes = real.read_bytes()
    client.post("/api/tickets", json={"title": "a", "text": "b"})
    client.delete("/api/tickets/t-2fa")
    assert real.read_bytes() == antes
    assert "t-2fa" not in (settings.catalog_dir / TICKETS_FILE).read_text(encoding="utf-8")
