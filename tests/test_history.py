"""Testes do histórico: serviço, ``GET /api/runs`` e ``GET /api/runs/{id}`` e os comandos ``history`` e ``show``."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.adapters.api.main import create_app
from app.adapters.cli.main import EXIT_NOT_FOUND, EXIT_OK, EXIT_USAGE, main
from app.adapters.storage.json_files import JsonRunRepo
from app.config import Settings
from app.container import build_container
from app.domain.errors import LLMUnavailable, NotFound, ValidationFailed
from app.domain.models import ContentType
from app.services.generators import GenerationContext, generate
from app.services.history import MAX_HISTORY_LIMIT, HistoryFilters, get_run, list_runs
from tests.support import LLMRoteirizado


class Relogio:
    """Relógio de teste que avança 1 s a cada leitura: cada execução tem um carimbo distinto e crescente."""

    def __init__(self) -> None:
        self._t = datetime(2026, 11, 20, 14, 0, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))

    def __call__(self, tz: ZoneInfo) -> datetime:
        self._t += timedelta(seconds=1)
        return self._t.astimezone(tz)


def _ctx(settings: Settings, llm=None, relogio: Relogio | None = None) -> GenerationContext:
    ctx = build_container(settings, llm=llm).generation
    return replace(ctx, clock=relogio or Relogio())


@pytest.fixture
def populado(settings: Settings):
    """Seis execuções em ordem conhecida (relógio compartilhado): 5 ok (uma é cache hit) e a mais recente com erro."""
    relogio = Relogio()
    ctx = _ctx(settings, relogio=relogio)
    feitas = {
        "marta_diag": generate(ctx, content_type=ContentType.DIAGNOSIS, profile_id="marta", ticket_id="t-2fa"),
        "marta_diag_hit": generate(ctx, content_type=ContentType.DIAGNOSIS, profile_id="marta", ticket_id="t-2fa"),
        "marta_passos": generate(ctx, content_type=ContentType.RESOLUTION_STEPS, profile_id="marta", ticket_id="t-2fa"),
        "bianca_csv": generate(ctx, content_type=ContentType.DIAGNOSIS, profile_id="bianca", ticket_id="t-csv"),
        "livre": generate(ctx, content_type=ContentType.FLOW_SUMMARY, profile_id="jorge", ticket_text="Relato livre."),
    }
    erro_ctx = _ctx(settings, LLMRoteirizado(LLMUnavailable("fora do ar")), relogio)
    with pytest.raises(LLMUnavailable):
        generate(erro_ctx, content_type=ContentType.DIAGNOSIS, profile_id="rafael", ticket_id="t-sync")
    return ctx, {k: v.record for k, v in feitas.items()}


def _ids(armazenadas) -> list[str]:
    return [s.record.run_id for s in armazenadas]


# --- serviço -------------------------------------------------------------------------------------------


def test_lista_do_mais_recente_para_o_mais_antigo(settings: Settings, populado) -> None:
    ctx, feitas = populado
    ordem = _ids(list_runs(ctx.runs))
    assert len(ordem) == 6
    # Os cinco geram carimbos crescentes (relógio de teste) e o de erro vem por último: é o mais recente.
    esperada = ("livre", "bianca_csv", "marta_passos", "marta_diag_hit", "marta_diag")
    assert ordem[1:] == [feitas[k].run_id for k in esperada]
    assert list_runs(ctx.runs)[0].record.status == "error"


@pytest.mark.parametrize(
    ("filtros", "esperadas"),
    [
        ({"customer_id": "marta"}, {"marta_diag", "marta_diag_hit", "marta_passos"}),
        ({"ticket_id": "t-csv"}, {"bianca_csv"}),
        ({"content_type": ContentType.DIAGNOSIS}, {"marta_diag", "marta_diag_hit", "bianca_csv", "ERRO"}),
        ({"prompt_version": "v1"}, {"marta_diag", "marta_diag_hit", "marta_passos", "bianca_csv", "livre", "ERRO"}),
        ({"prompt_version": "v9"}, set()),
        ({"status": "error"}, {"ERRO"}),
        (
            {"status": "ok", "customer_id": "marta", "content_type": ContentType.DIAGNOSIS},
            {"marta_diag", "marta_diag_hit"},
        ),
        ({"ticket_id": "nao-existe"}, set()),
    ],
)
def test_filtros_combinam_por_igualdade(populado, filtros: dict, esperadas: set[str]) -> None:
    ctx, feitas = populado
    achadas = list_runs(ctx.runs, HistoryFilters(**filtros))
    por_id = {r.run_id: nome for nome, r in feitas.items()}
    nomes = {por_id.get(s.record.run_id, "ERRO") for s in achadas}
    assert nomes == esperadas


def test_filtra_por_cache_key_inteira_e_por_prefixo_e_acha_as_equivalentes(populado) -> None:
    ctx, feitas = populado
    chave = feitas["marta_diag"].cache_key
    equivalentes = {feitas["marta_diag"].run_id, feitas["marta_diag_hit"].run_id}
    assert set(_ids(list_runs(ctx.runs, HistoryFilters(cache_key=chave)))) == equivalentes
    assert set(_ids(list_runs(ctx.runs, HistoryFilters(cache_key=chave[:12].upper())))) == equivalentes
    assert list_runs(ctx.runs, HistoryFilters(cache_key="0" * 64)) == []


def test_cache_key_tambem_localiza_execucao_com_erro_e_sem_cache(settings: Settings) -> None:
    ctx = _ctx(settings, LLMRoteirizado(LLMUnavailable("x")))
    with pytest.raises(LLMUnavailable):
        generate(ctx, content_type=ContentType.DIAGNOSIS, profile_id="marta", ticket_id="t-2fa")
    sem_cache = generate(_ctx(settings), content_type=ContentType.DIAGNOSIS, profile_id="marta", ticket_id="t-2fa",
                         use_cache=False).record
    achadas = list_runs(ctx.runs, HistoryFilters(cache_key=sem_cache.cache_key))
    assert {s.record.status for s in achadas} == {"error", "ok"}


def test_limite_corta_mantendo_as_mais_recentes(populado) -> None:
    ctx, _ = populado
    todas = _ids(list_runs(ctx.runs))
    assert _ids(list_runs(ctx.runs, limit=2)) == todas[:2]
    assert len(list_runs(ctx.runs, limit=1)) == 1


@pytest.mark.parametrize("limite", [0, -1, MAX_HISTORY_LIMIT + 1])
def test_limite_fora_da_faixa_e_validation_failed(populado, limite: int) -> None:
    ctx, _ = populado
    with pytest.raises(ValidationFailed, match="limite"):
        list_runs(ctx.runs, limit=limite)


def test_historico_vazio(settings: Settings) -> None:
    assert list_runs(JsonRunRepo(settings.data_dir)) == []


def test_get_run_devolve_o_registro_e_not_found_para_id_inexistente(populado) -> None:
    ctx, feitas = populado
    stored = get_run(ctx.runs, feitas["livre"].run_id)
    assert stored.record == feitas["livre"] and stored.saved_path.endswith(f"{feitas['livre'].run_id}.json")
    with pytest.raises(NotFound):
        get_run(ctx.runs, "0" * 12)


# --- API -----------------------------------------------------------------------------------------------


@pytest.fixture
def cliente(settings: Settings, populado) -> TestClient:
    return TestClient(create_app(build_container(settings), frontend_dist=None))


def test_api_lista_o_resumo_sem_a_saida_pesada(cliente: TestClient) -> None:
    r = cliente.get("/api/runs")
    assert r.status_code == 200
    linhas = r.json()
    assert len(linhas) == 6 and linhas[0]["status"] == "error" and linhas[0]["error"]["type"] == "LLMUnavailable"
    primeira = linhas[1]
    assert {"run_id", "timestamp", "customer_name", "ticket_title", "content_type", "prompt_version", "cache_hit",
            "cache_key", "latency_ms", "saved_path"} <= set(primeira)
    assert "output" not in primeira and "prompt_messages" not in primeira
    assert next(x for x in linhas if x["ticket_id"] is None)["ticket_title"] == "Ticket digitado"


@pytest.mark.parametrize(
    ("query", "quantidade"),
    [
        ("customer_id=marta", 3), ("ticket_id=t-csv", 1), ("content_type=diagnosis", 4), ("prompt_version=v1", 6),
        ("status=error", 1), ("status=ok&customer_id=marta", 3), ("limit=2", 2), ("customer_id=nao-existe", 0),
    ],
)
def test_api_filtros_e_limite(cliente: TestClient, query: str, quantidade: int) -> None:
    assert len(cliente.get(f"/api/runs?{query}").json()) == quantidade


def test_api_filtra_por_cache_key(cliente: TestClient) -> None:
    hit = next(x for x in cliente.get("/api/runs").json() if x["cache_hit"])
    achadas = cliente.get(f"/api/runs?cache_key={hit['cache_key']}").json()
    assert len(achadas) == 2 and {x["cache_hit"] for x in achadas} == {True, False}
    assert next(x for x in achadas if x["cache_hit"])["source_run_id"] == next(
        x for x in achadas if not x["cache_hit"])["run_id"]


@pytest.mark.parametrize("query", ["content_type=poema", "status=talvez", "limit=0", "limit=501", "limit=abc"])
def test_api_filtro_invalido_e_422(cliente: TestClient, query: str) -> None:
    assert cliente.get(f"/api/runs?{query}").status_code == 422


def test_api_detalhe_traz_registro_completo_e_caminho(cliente: TestClient) -> None:
    resumo = next(x for x in cliente.get("/api/runs?content_type=resolution_steps").json())
    r = cliente.get(f"/api/runs/{resumo['run_id']}")
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["saved_path"] == resumo["saved_path"]
    assert corpo["run"]["run_id"] == resumo["run_id"] and corpo["run"]["output"]["steps"]
    assert corpo["run"]["prompt_messages"]


def test_api_detalhe_de_execucao_com_erro(cliente: TestClient) -> None:
    erro = cliente.get("/api/runs?status=error").json()[0]
    corpo = cliente.get(f"/api/runs/{erro['run_id']}").json()
    assert corpo["run"]["status"] == "error" and corpo["run"]["output"] is None


@pytest.mark.parametrize("run_id", ["000000000000", "nao-existe", "..", "%2E%2E", "*", "AAAAAAAAAAAA"])
def test_api_detalhe_inexistente_ou_malformado_e_404(cliente: TestClient, run_id: str) -> None:
    r = cliente.get(f"/api/runs/{run_id}")
    assert r.status_code == 404


def test_api_historico_vazio(settings: Settings) -> None:
    assert TestClient(create_app(build_container(settings), frontend_dist=None)).get("/api/runs").json() == []


def test_meta_traz_o_limite_padrao_do_historico(cliente: TestClient) -> None:
    assert cliente.get("/api/meta").json()["limits"]["history_limit"] == 50


# --- CLI -----------------------------------------------------------------------------------------------


@pytest.fixture
def container(settings: Settings, populado):
    return build_container(settings)


def test_cli_history_imprime_tabela_do_mais_recente_ao_mais_antigo(container, capsys) -> None:
    assert main(["history"], container) == EXIT_OK
    linhas = capsys.readouterr().out.splitlines()
    assert linhas[0].split() == [
        "ID", "QUANDO", "CLIENTE", "TICKET", "TIPO", "VER", "STATUS", "CACHE", "LATÊNCIA", "CHAVE",
    ]
    assert len(linhas) == 7
    assert "erro" in linhas[1] and "rafael" in linhas[1]
    assert any("hit" in linha for linha in linhas[1:]) and any("(livre)" in linha for linha in linhas[1:])
    assert "2026-11-20 14:" in linhas[2]  # horário no fuso do registro, sem deslocamento


def test_cli_history_filtros(container, capsys) -> None:
    assert main(["history", "--customer", "marta", "--type", "diagnosis", "--status", "ok"], container) == EXIT_OK
    assert len(capsys.readouterr().out.splitlines()) == 3  # cabeçalho + 2


def test_cli_history_cache_key_lista_as_equivalentes(container, capsys) -> None:
    main(["history", "--json"], container)
    runs = [x["run"] for x in json.loads(capsys.readouterr().out)]
    chave = next(r["cache_key"] for r in runs if r["cache_hit"])
    assert main(["history", "--cache-key", chave[:12]], container) == EXIT_OK
    linhas = capsys.readouterr().out.splitlines()
    assert len(linhas) == 3 and all(chave[:12] in linha for linha in linhas[1:])


def test_cli_history_vazio_e_limite(container, settings, capsys) -> None:
    assert main(["history", "--customer", "ninguem"], container) == EXIT_OK
    assert "Nenhuma execução encontrada." in capsys.readouterr().out
    assert main(["history", "--limit", "2"], container) == EXIT_OK
    assert len(capsys.readouterr().out.splitlines()) == 3


def test_cli_history_limite_invalido_e_erro_de_uso(container, capsys) -> None:
    assert main(["history", "--limit", "0"], container) == EXIT_USAGE
    assert "limite" in capsys.readouterr().err


def test_cli_history_tipo_invalido_e_erro_de_uso(container) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["history", "--type", "all"], container)
    assert exc.value.code == EXIT_USAGE


def test_cli_history_json(container, capsys) -> None:
    assert main(["history", "--status", "error", "--json"], container) == EXIT_OK
    [item] = json.loads(capsys.readouterr().out)
    assert item["run"]["status"] == "error" and item["saved_path"].endswith(".json")


def test_cli_show_reaproveita_o_renderizador_do_generate(container, capsys) -> None:
    assert main(["generate", "--customer", "bianca", "--ticket", "t-sync", "--type", "flow_summary",
                 "--no-cache"], container) == EXIT_OK
    gerado = capsys.readouterr().out
    run_id = next(x for x in gerado.splitlines() if x.startswith("Execução:")).split()[1]
    assert main(["show", run_id], container) == EXIT_OK
    mostrado = capsys.readouterr().out
    assert mostrado == gerado  # byte a byte: o `show` imprime o mesmo que o `generate` imprimiu


def test_cli_show_de_cache_hit_e_de_erro(container, capsys) -> None:
    main(["history", "--json"], container)
    itens = [x["run"] for x in json.loads(capsys.readouterr().out)]
    hit = next(r for r in itens if r["cache_hit"])
    assert main(["show", hit["run_id"]], container) == EXIT_OK
    saida = capsys.readouterr().out
    assert f"cache hit (origem {hit['source_run_id']}" in saida and "HIPÓTESES" in saida
    erro = next(r for r in itens if r["status"] == "error")
    assert main(["show", erro["run_id"]], container) == EXIT_OK
    assert "FALHOU: fora do ar" in capsys.readouterr().out


def test_cli_show_json(container, capsys) -> None:
    main(["history", "--limit", "1", "--json"], container)
    run_id = json.loads(capsys.readouterr().out)[0]["run"]["run_id"]
    assert main(["show", run_id, "--json"], container) == EXIT_OK
    assert json.loads(capsys.readouterr().out)["run"]["run_id"] == run_id


@pytest.mark.parametrize("run_id", ["000000000000", "nao-existe", "../x"])
def test_cli_show_inexistente_retorna_codigo_2(container, capsys, run_id: str) -> None:
    assert main(["show", run_id], container) == EXIT_NOT_FOUND
    assert "não encontrada" in capsys.readouterr().err
