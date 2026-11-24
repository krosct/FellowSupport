"""Testes do CRUD de prompts: armazenamento, serviço, API HTTP e CLI."""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.adapters.api.main import create_app
from app.adapters.cli.main import EXIT_NOT_FOUND, EXIT_OK, EXIT_USAGE, main
from app.adapters.storage.prompt_files import FilePromptStore
from app.config import BASE_DIR, Settings
from app.container import build_container
from app.domain.errors import NotFound, ValidationFailed
from app.domain.prompting.registry import PromptChange, PromptRegistry, compute_content_sha256, next_version_name
from app.services.prompts import create_prompt, delete_prompt, get_prompt
from tests.support import cli


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(build_container(settings), frontend_dist=None))


@pytest.fixture
def container(settings: Settings):
    return build_container(settings)


def _v1_files(settings: Settings) -> dict[str, str]:
    store = FilePromptStore(settings.prompts_dir)
    return {name: store.read_text("v1", name) for name in store.list_files("v1")}


# --- serviço e armazenamento -----------------------------------------------------------------------


def test_create_calcula_hash_e_grava_arquivos_na_pasta(settings: Settings) -> None:
    store = FilePromptStore(settings.prompts_dir)
    registry = PromptRegistry(store)
    esperada = next_version_name(store.list_versions())
    files = _v1_files(settings)
    files["system.md"] = "Persona customizada do $product_name."
    created = create_prompt(
        store,
        registry,
        based_on="v1",
        description="  Versão de teste  ",
        changes=[PromptChange(what="Ajuste persona", why="Clareza", expected_effect="Melhoria")],
        files=files,
        timezone=settings.app_timezone,
    )
    assert created.version == esperada
    assert created.based_on == "v1"
    assert created.description == "Versão de teste"
    assert created.is_default is True
    assert created.content_sha256 == compute_content_sha256(created.files)
    assert registry.verify(esperada) is True
    assert (settings.prompts_dir / esperada / "meta.json").is_file()
    assert (settings.prompts_dir / esperada / "system.md").read_text(encoding="utf-8") == files["system.md"]


def test_create_exige_source_valido(settings: Settings) -> None:
    store = FilePromptStore(settings.prompts_dir)
    registry = PromptRegistry(store)
    files = _v1_files(settings)
    with pytest.raises(ValidationFailed, match="source"):
        create_prompt(
            store, registry, based_on="  ", description="x", changes=[], files=files, timezone=settings.app_timezone
        )
    with pytest.raises(NotFound):
        create_prompt(
            store, registry, based_on="v99", description="x", changes=[], files=files, timezone=settings.app_timezone
        )


def test_edicao_de_prompt_nao_existe_e_versoes_sao_imutaveis(client: TestClient) -> None:
    v1 = client.get("/api/prompts/v1").json()
    assert client.put(
        "/api/prompts/v1", json={"description": "Alterada", "changes": [], "files": v1["files"]}
    ).status_code in (404, 405)
    with pytest.raises(SystemExit) as exc:
        main(["prompt", "update", "v1"])
    assert exc.value.code == EXIT_USAGE


def test_create_exige_todos_os_arquivos_obrigatorios_e_placeholders_validos(client: TestClient) -> None:
    v1 = client.get("/api/prompts/v1").json()
    for faltando in ("system.md", "context.md", "adaptation.json", "repair.md", "diagnosis.md"):
        incompleto = {k: v for k, v in v1["files"].items() if k != faltando}
        r = client.post(
            "/api/prompts", json={"based_on": "v1", "description": "Incompleta", "changes": [], "files": incompleto}
        )
        assert r.status_code == 422 and faltando in r.json()["detail"]

    # Placeholder exclusivo de outro tipo em diagnosis.md é recusado.
    errado = {**v1["files"], "diagnosis.md": "Use $min_steps aqui."}
    r_var = client.post(
        "/api/prompts", json={"based_on": "v1", "description": "Var errada", "changes": [], "files": errado}
    )
    assert r_var.status_code == 422 and "Placeholder desconhecido" in r_var.json()["detail"]


def test_delete_recusa_v1_e_apaga_pasta_de_versao_derivada(settings: Settings) -> None:
    store = FilePromptStore(settings.prompts_dir)
    registry = PromptRegistry(store)
    criada = create_prompt(
        store,
        registry,
        based_on="v1",
        description="versão derivada",
        changes=[],
        files=_v1_files(settings),
        timezone=settings.app_timezone,
    )
    with pytest.raises(ValidationFailed, match="v1"):
        delete_prompt(store, registry, "v1")
    assert (settings.prompts_dir / "v1").is_dir()

    removed = delete_prompt(store, registry, criada.version)
    assert removed.version == criada.version
    assert not (settings.prompts_dir / criada.version).exists()
    with pytest.raises(NotFound):
        get_prompt(registry, criada.version)


def test_criacoes_concorrentes_geram_versoes_distintas(settings: Settings) -> None:
    store = FilePromptStore(settings.prompts_dir)
    registry = PromptRegistry(store)
    inicial = int(next_version_name(store.list_versions())[1:])
    files = _v1_files(settings)

    def _criar(i: int) -> str:
        return create_prompt(
            store, registry, based_on="v1", description=f"Concorrente {i}", changes=[], files=files,
            timezone=settings.app_timezone,
        ).version

    with ThreadPoolExecutor(max_workers=4) as pool:
        versoes = list(pool.map(_criar, range(4)))
    assert len(set(versoes)) == 4
    assert sorted(versoes, key=lambda v: int(v[1:])) == [f"v{n}" for n in range(inicial, inicial + 4)]


# --- rotas HTTP ------------------------------------------------------------------------------------


def test_api_crud_de_prompts_e_atualizacao_de_meta(client: TestClient, settings: Settings) -> None:
    padrao_anterior = client.get("/api/meta").json()["default_prompt_version"]
    v1 = client.get("/api/prompts/v1").json()
    assert v1["version"] == "v1" and "system.md" in v1["files"]

    # Sem based_on responde 422.
    sem_source = client.post(
        "/api/prompts", json={"based_on": "", "description": "x", "changes": [], "files": v1["files"]}
    )
    assert sem_source.status_code == 422

    # Cria uma nova versão derivada a partir de v1.
    novo_files = {**v1["files"], "system.md": "Nova persona do $product_name."}
    criado_resp = client.post(
        "/api/prompts",
        json={
            "based_on": "v1",
            "description": "Prompt derivado",
            "changes": [{"what": "Persona", "why": "Teste", "expected_effect": "Mais clareza"}],
            "files": novo_files,
        },
    )
    assert criado_resp.status_code == 201
    criado = criado_resp.json()
    nova = criado["version"]
    assert nova != "v1" and criado["based_on"] == "v1" and criado["is_default"] is True
    assert client.get("/api/meta").json()["default_prompt_version"] == nova

    # Gera conteúdo usando o prompt recém-criado.
    gen = client.post("/api/generate", json={"profile_id": "marta", "ticket_id": "t-2fa", "prompt_version": nova})
    assert gen.status_code == 200
    assert gen.json()["run"]["prompt_sha256"] == criado["content_sha256"]

    # v1 não pode ser removida (e PUT não existe mais).
    assert (
        client.put(
            "/api/prompts/v1",
            json={"description": "v1 editada", "changes": [], "files": v1["files"]},
        ).status_code
        in (404, 405)
    )
    assert client.delete("/api/prompts/v1").status_code == 422

    # Remove a versão recém-criada e confere que meta volta para a padrão anterior e a pasta some.
    del_resp = client.delete(f"/api/prompts/{nova}")
    assert del_resp.status_code == 200 and del_resp.json()["version"] == nova
    assert not (settings.prompts_dir / nova).exists()
    assert client.get(f"/api/prompts/{nova}").status_code == 404
    assert client.get("/api/meta").json()["default_prompt_version"] == padrao_anterior


def test_api_nao_altera_prompts_reais_do_repositorio(client: TestClient) -> None:
    real_v1 = BASE_DIR / "prompts" / "v1" / "meta.json"
    antes_v1 = real_v1.read_bytes()
    antes_pastas = sorted(p.name for p in (BASE_DIR / "prompts").iterdir())
    v1 = client.get("/api/prompts/v1").json()
    client.post("/api/prompts", json={"based_on": "v1", "description": "Teste", "changes": [], "files": v1["files"]})
    assert real_v1.read_bytes() == antes_v1
    assert sorted(p.name for p in (BASE_DIR / "prompts").iterdir()) == antes_pastas


def test_api_recusa_adaptation_invalido_e_placeholder_desconhecido(client: TestClient) -> None:
    v1 = client.get("/api/prompts/v1").json()
    bad_adapt = {**v1["files"], "adaptation.json": "{json invalido"}
    r1 = client.post("/api/prompts", json={"based_on": "v1", "description": "x", "changes": [], "files": bad_adapt})
    assert r1.status_code == 422 and "adaptation.json" in r1.json()["detail"]

    bad_tpl = {**v1["files"], "diagnosis.md": "Usa $variavel_inexistente aqui"}
    r2 = client.post("/api/prompts", json={"based_on": "v1", "description": "x", "changes": [], "files": bad_tpl})
    assert r2.status_code == 422 and "Placeholder desconhecido" in r2.json()["detail"]


# --- CLI -------------------------------------------------------------------------------------------


def test_cli_prompt_list_e_remocao_do_comando_versions(container, capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["versions"])
    assert exc.value.code == EXIT_USAGE

    assert cli(["prompt", "list"], container) == EXIT_OK
    inicial = capsys.readouterr().out
    assert "v1" in inicial and "(padrão)" in inicial

    assert cli(["prompt", "list", "--json"], container) == EXIT_OK
    antes = [i["version"] for i in json.loads(capsys.readouterr().out)]

    # Cria nova versão e confere listagem, --details e --json via prompt list.
    cli(
        [
            "prompt", "create", "--based-on", "v1", "--description", "Versão derivada",
            "--what", "Ajuste", "--why", "Evidência", "--expected-effect", "Melhoria",
        ],
        container,
    )
    capsys.readouterr()

    assert cli(["prompt", "list", "--json"], container) == EXIT_OK
    itens = json.loads(capsys.readouterr().out)
    nova = itens[-1]["version"]
    assert [i["version"] for i in itens] == [*antes, nova]
    assert all(not i["is_default"] for i in itens[:-1]) and itens[-1]["is_default"] is True

    assert cli(["prompt", "list", "--details"], container) == EXIT_OK
    detalhes = capsys.readouterr().out
    assert "(padrão)" in detalhes and f"O que mudou na {nova} em relação à v1" in detalhes
    assert "Por quê: Evidência" in detalhes and "Efeito esperado: Melhoria" in detalhes


def test_cli_prompt_create_exige_based_on() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["prompt", "create", "--description", "Sem base"])
    assert exc.value.code == EXIT_USAGE


def test_cli_prompt_crud_completo(container, settings: Settings, capsys, tmp_path: Path, monkeypatch) -> None:
    arquivo_local = tmp_path / "novo_system.md"
    arquivo_local.write_text("Persona via arquivo do $product_name.", encoding="utf-8")

    # Create
    assert cli(
        [
            "prompt", "create", "--based-on", "v1", "--description", "Via CLI",
            "--file", f"system.md={arquivo_local}", "--json",
        ],
        container,
    ) == EXIT_OK
    criado = json.loads(capsys.readouterr().out)
    nova = criado["version"]
    assert nova != "v1" and criado["based_on"] == "v1"
    assert criado["files"]["system.md"] == "Persona via arquivo do $product_name."
    assert container.prompts.verify(nova) is True

    # List por id
    assert cli(["prompt", "list", "--id", nova], container) == EXIT_OK
    assert f"Versão:    {nova} (padrão)" in capsys.readouterr().out

    # Delete v1 recusado
    assert cli(["prompt", "delete", "v1", "--yes"], container) == EXIT_USAGE
    assert "v1" in capsys.readouterr().err

    # Delete da versão criada cancelado sem confirmar
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    assert cli(["prompt", "delete", nova], container) == EXIT_OK
    assert "Remoção cancelada" in capsys.readouterr().out
    assert (settings.prompts_dir / nova).is_dir()

    # Delete da versão criada confirmado
    assert cli(["prompt", "delete", nova, "--yes", "--json"], container) == EXIT_OK
    removido = json.loads(capsys.readouterr().out)
    assert removido["version"] == nova
    assert not (settings.prompts_dir / nova).exists()
    assert cli(["prompt", "list", "--id", nova], container) == EXIT_NOT_FOUND
