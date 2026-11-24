"""Testes da API de avaliação e comparação (TestClient, sem rede): comparisons e o fim do compare que gerava."""

from dataclasses import replace
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.adapters.api.main import create_app
from app.config import Settings
from app.container import build_container
from app.domain import rubric
from tests.support import FakeContador

CENARIO = {"profile_id": "marta", "ticket_id": "t-2fa", "content_type": "resolution_steps"}


def notas(base: int = 4) -> dict:
    # Monta notas válidas para todos os critérios da rubrica.
    return {key: {"score": base, "justification": f"Motivo de {key}."} for key in rubric.CRITERIA_KEYS}


def _cliente(settings: Settings, llm=None) -> TestClient:
    return TestClient(create_app(build_container(settings, llm=llm), frontend_dist=None))


@pytest.fixture
def cliente(settings: Settings) -> TestClient:
    return _cliente(settings)


def _comparar(cliente: TestClient, versoes=("v1", "v2"), **extra) -> list[dict]:
    """Gera o cenário padrão em cada versão pela API (como a aba Gerar) e devolve ``{saved_path, run}`` de cada uma."""
    from tests.support import seed_prompt_versions

    prompts_dir = cliente.app.state.container.settings.prompts_dir  # type: ignore[union-attr]
    seed_prompt_versions(prompts_dir, *versoes)
    runs = []
    for versao in versoes:
        r = cliente.post("/api/generate", json={**CENARIO, "prompt_version": versao, **extra})
        assert r.status_code == 200, r.text
        runs.append(r.json())
    return runs


def test_meta_publica_a_rubrica_e_os_limites_da_comparacao(cliente: TestClient) -> None:
    meta = cliente.get("/api/meta").json()
    assert meta["rubric"]["justification_max_chars"] == rubric.JUSTIFICATION_MAX_CHARS
    rotulos = {"1": "insuficiente", "2": "fraco", "3": "adequado", "4": "bom", "5": "excelente"}
    assert meta["rubric"]["total_max"] == 15
    assert meta["rubric"]["scale"] == {"min": 1, "max": 5, "labels": rotulos}
    assert [c["key"] for c in meta["rubric"]["criteria"]] == list(rubric.CRITERIA_KEYS)
    assert meta["limits"]["min_compared_versions"] == 2 and meta["limits"]["conclusion_max_chars"] == 1000


# --- rotas removidas: comparar não gera e a nota só é dada dentro da comparação (ADR 0040) ------------------


def test_nao_existe_rota_que_gera_na_comparacao_nem_avaliacao_avulsa(cliente: TestClient) -> None:
    run_id = _comparar(cliente)[0]["run"]["run_id"]
    assert cliente.post("/api/compare", json={**CENARIO, "versions": ["v1", "v2"]}).status_code in (404, 405)
    assert cliente.put(f"/api/runs/{run_id}/evaluation", json=notas()).status_code in (404, 405)


# --- /api/comparisons ----------------------------------------------------------------------------------------


def _salvar(cliente: TestClient, runs: list[dict], **extra) -> dict:
    ids = [r["run"]["run_id"] for r in runs]
    evaluations = {ids[0]: notas(3), ids[1]: notas(4)}
    r = cliente.post("/api/comparisons", json={"run_ids": ids, "evaluations": evaluations, **extra})
    assert r.status_code == 200, r.text
    return r.json()


def test_salva_lista_e_abre_a_comparacao(cliente: TestClient, settings: Settings) -> None:
    salva = _salvar(cliente, _comparar(cliente), conclusion="A v2 serviu melhor.")
    comparacao = salva["comparison"]
    assert salva["saved_path"].endswith(f"{comparacao['comparison_id']}.json")
    assert comparacao["winner"] == "v2" and comparacao["conclusion"] == "A v2 serviu melhor."
    assert [v["total"] for v in comparacao["versions"]] == [9, 12]
    assert comparacao["versions"][0]["evaluation"]["clarity"]["justification"] == "Motivo de clarity."
    assert comparacao["scenario"]["customer_id"] == "marta"

    [linha] = cliente.get("/api/comparisons").json()
    assert linha["comparison_id"] == comparacao["comparison_id"] and linha["winner"] == "v2"
    assert linha["customer_name"] == "Dona Marta" and linha["content_type"] == "resolution_steps"
    assert linha["versions"] == [{"prompt_version": "v1", "total": 9}, {"prompt_version": "v2", "total": 12}]
    assert "output" not in str(linha)  # a listagem não carrega as saídas

    aberta = cliente.get(f"/api/comparisons/{comparacao['comparison_id']}").json()
    assert aberta["comparison"] == comparacao and aberta["saved_path"] == salva["saved_path"]


def test_salvar_exige_avaliacao_de_todas_as_execucoes_e_notas_validas(cliente: TestClient) -> None:
    runs = _comparar(cliente)
    ids = [r["run"]["run_id"] for r in runs]
    sem_notas = cliente.post("/api/comparisons", json={"run_ids": ids})
    assert sem_notas.status_code == 422 and "evaluations" in sem_notas.text
    sem_um_lado = cliente.post("/api/comparisons", json={"run_ids": ids, "evaluations": {ids[0]: notas()}})
    assert sem_um_lado.status_code == 422 and "não tem avaliação" in sem_um_lado.json()["detail"]
    ruim = notas()
    ruim["clarity"]["score"] = 9
    fora = cliente.post("/api/comparisons", json={"run_ids": ids, "evaluations": {ids[0]: ruim, ids[1]: notas()}})
    assert fora.status_code == 422 and "inteiro de 1 a 5" in fora.json()["detail"]
    assert cliente.get("/api/comparisons").json() == []


def test_salvar_recusa_cenarios_diferentes(cliente: TestClient) -> None:
    a = _comparar(cliente)[0]["run"]["run_id"]
    outro = _comparar(cliente, ("v2",), profile_id="bianca")[0]["run"]["run_id"]
    r = cliente.post("/api/comparisons", json={
        "run_ids": [a, outro], "evaluations": {a: notas(), outro: notas()}})
    assert r.status_code == 422 and "perfil do cliente (v1: marta, v2: bianca)" in r.json()["detail"]


def test_comparacoes_erros_de_id_e_limite(cliente: TestClient) -> None:
    assert cliente.get("/api/comparisons/aaaaaaaaaaaa").status_code == 404
    assert cliente.get("/api/comparisons/..%2Fx").status_code == 404
    assert cliente.get("/api/comparisons?limit=0").status_code == 422
    assert cliente.get("/api/comparisons?limit=501").status_code == 422
    assert cliente.get("/api/comparisons?offset=-1").status_code == 422
    r = cliente.post("/api/comparisons", json={"run_ids": ["aaaaaaaaaaaa", "bbbbbbbbbbbb"], "evaluations": {}})
    assert r.status_code == 404


def test_listagem_de_comparacoes_e_paginada_com_o_total_no_cabecalho(settings: Settings) -> None:
    container = build_container(settings)
    relogio = iter(range(10, 20))
    container = replace(
        container,
        comparison=replace(
            container.comparison, clock=lambda tz: datetime(2026, 11, 20, 12, next(relogio), 0, tzinfo=tz)
        ),
    )
    cliente = TestClient(create_app(container, frontend_dist=None))
    salvas = [_salvar(cliente, _comparar(cliente, use_cache=False, confirm_replace=True)) for _ in range(3)]
    ids = [s["comparison"]["comparison_id"] for s in reversed(salvas)]  # da mais recente para a mais antiga
    primeira = cliente.get("/api/comparisons", params={"limit": 2})
    assert primeira.headers["x-total-count"] == "3" and [c["comparison_id"] for c in primeira.json()] == ids[:2]
    segunda = cliente.get("/api/comparisons", params={"limit": 2, "offset": 2})
    assert segunda.headers["x-total-count"] == "3" and [c["comparison_id"] for c in segunda.json()] == ids[2:]


# --- GET /api/comparisons/lookup (cache das comparações, ADR 0038) -----------------------------------------


def _procurar(cliente: TestClient, ids: list[str]):
    return cliente.get("/api/comparisons/lookup", params={"run_ids": ids})


def test_lookup_devolve_a_comparacao_salva_das_mesmas_execucoes_em_qualquer_ordem(cliente: TestClient) -> None:
    runs = _comparar(cliente)
    ids = [r["run"]["run_id"] for r in runs]
    assert _procurar(cliente, ids).json() is None  # nada salvo ainda
    salva = _salvar(cliente, runs)
    for ordem in (ids, ids[::-1]):
        achada = _procurar(cliente, ordem)
        assert achada.status_code == 200 and achada.json() == salva


def test_lookup_devolve_a_mais_recente_e_ignora_outro_conjunto_de_execucoes(settings: Settings) -> None:
    container = build_container(settings)
    relogio = iter(range(10, 20))  # relógio de teste: duas gravações no mesmo segundo não empatam na ordenação
    container = replace(
        container,
        comparison=replace(
            container.comparison, clock=lambda tz: datetime(2026, 11, 20, 12, next(relogio), 0, tzinfo=tz)
        ),
    )
    cliente = TestClient(create_app(container, frontend_dist=None))
    runs = _comparar(cliente)
    ids = [r["run"]["run_id"] for r in runs]
    primeira = _salvar(cliente, runs)
    segunda = _salvar(cliente, runs)
    assert primeira["comparison"]["comparison_id"] != segunda["comparison"]["comparison_id"]
    assert _procurar(cliente, ids).json()["comparison"]["comparison_id"] == segunda["comparison"]["comparison_id"]
    outras = _comparar(cliente, use_cache=False, confirm_replace=True)
    assert _procurar(cliente, [r["run"]["run_id"] for r in outras]).json() is None  # outras execuções, outra comparação


def test_lookup_nao_chama_o_llm_e_valida_a_entrada(settings: Settings) -> None:
    llm = FakeContador()
    cliente = _cliente(settings, llm)
    runs = _comparar(cliente)
    ids = [r["run"]["run_id"] for r in runs]
    _salvar(cliente, runs)
    chamadas = llm.chamadas
    assert _procurar(cliente, ids).json() is not None and llm.chamadas == chamadas
    assert _procurar(cliente, ids[:1]).status_code == 422
    assert _procurar(cliente, [ids[0], ids[0]]).status_code == 422
    assert cliente.get("/api/comparisons/lookup").status_code == 422  # sem run_ids
