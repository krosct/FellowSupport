"""Testes da CLI de comparação e rubrica (ADR 0041): ``compare`` (não gera; carrega a salva ou avalia do zero),
``history comparison`` (ou ``list``) e ``history comparison show``. A CLI chama via ``Container``."""

import json
import os
import shutil
import subprocess
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest

from app.adapters.cli.main import EXIT_NOT_FOUND, EXIT_OK, EXIT_USAGE
from app.config import BASE_DIR, Settings
from app.container import Container, build_container
from app.domain import rubric
from tests.support import cli, gerar_versoes


@pytest.fixture
def container(settings: Settings) -> Container:
    return build_container(settings)


def notas(base: int) -> dict:
    """Notas válidas em todos os critérios."""
    return {key: {"score": base, "justification": f"Motivo de {key}."} for key in rubric.CRITERIA_KEYS}


def arquivo_de_notas(tmp_path: Path, por_execucao: dict[str, int]) -> str:
    """Grava o arquivo do ``--evaluations`` (``{run_id: notas}``) e devolve o caminho."""
    caminho = tmp_path / "notas.json"
    caminho.write_text(json.dumps({run_id: notas(base) for run_id, base in por_execucao.items()}), encoding="utf-8")
    return str(caminho)


# Respostas do terminal para avaliar duas versões: dá 3 em tudo na v1 e 5 em tudo na v2.
RESPOSTAS_V1 = ["3", "Clara.", "3", "Ok.", "3", "Vago."]
RESPOSTAS_V2 = ["5", "Ótima.", "5", "Perfeita.", "5", "Diz o que fazer."]


def responder(monkeypatch, respostas: list[str]) -> list[str]:
    """Responde as perguntas do terminal na ordem e guarda os textos perguntados."""
    fila = iter(respostas)
    perguntas: list[str] = []

    def entrada(prompt: str = "") -> str:
        perguntas.append(prompt)
        return next(fila)

    monkeypatch.setattr("builtins.input", entrada)
    return perguntas


def sem_terminal(monkeypatch) -> None:
    """Simula stdin fechado (sem terminal para responder)."""

    def fechado(prompt: str = "") -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", fechado)


# --- compare: avaliação nova ---------------------------------------------------------------------------------


def test_compare_nao_gera_avalia_no_terminal_e_salva(container, capsys, monkeypatch, settings) -> None:
    v1, v2 = gerar_versoes(container)
    antes = sorted((settings.data_dir / "runs").rglob("*.json"))
    perguntas = responder(monkeypatch, [*RESPOSTAS_V1, *RESPOSTAS_V2, "A v2 serviu melhor."])
    assert cli(["compare", v1, v2], container) == EXIT_OK
    saida = capsys.readouterr().out
    assert sorted((settings.data_dir / "runs").rglob("*.json")) == antes  # nada foi gerado
    avaliacao = saida.split("Comparação salva.")[0]
    assert avaliacao.count("Cliente: Dona Marta") == 1 and "O que mudou na v2 em relação à v1" in avaliacao
    assert saida.index("VERSÃO v1") < saida.index("VERSÃO v2") and "Escala: 1 = insuficiente" in saida
    assert "Comparação salva." in saida and "VENCEDOR: versão v2 (v1=9 v2=15; máximo 15)" in saida
    assert "Conclusão (candidato): A v2 serviu melhor." in saida
    assert perguntas[0].startswith("Nota de")
    assert container.runs.get(v2).record.evaluation["clarity"]["score"] == 5


def test_compare_repete_a_pergunta_se_a_resposta_for_invalida(container, capsys, monkeypatch) -> None:
    v1, v2 = gerar_versoes(container)
    respostas = ["0", "abc", "4", "", "ok", "4", "b", "4", "c", *RESPOSTAS_V1, ""]
    responder(monkeypatch, respostas)
    assert cli(["compare", v1, v2], container) == EXIT_OK
    saida = capsys.readouterr().out
    assert saida.count("Informe um número inteiro de 1 a 5.") == 2
    assert saida.count("A justificativa é obrigatória.") == 1
    assert "Conclusão (automática)" in saida


def test_compare_por_arquivo_e_json(container, capsys, tmp_path) -> None:
    v1, v2 = gerar_versoes(container)
    args = ["compare", v1, v2, "--evaluations", arquivo_de_notas(tmp_path, {v1: 4, v2: 4}), "--json"]
    assert cli(args, container) == EXIT_OK
    salvo = json.loads(capsys.readouterr().out)
    assert salvo["comparison"]["winner"] is None and [v["total"] for v in salvo["comparison"]["versions"]] == [12, 12]


@pytest.mark.parametrize(
    ("quais", "codigo", "trecho"),
    [
        ("uma", EXIT_USAGE, "ao menos 2"),
        ("repetidas", EXIT_USAGE, "diferentes entre si"),
        ("inexistente", EXIT_NOT_FOUND, "não encontrada"),
        ("cache", EXIT_USAGE, "veio do cache"),
        ("mesma_versao", EXIT_USAGE, "As versões comparadas devem ser diferentes"),
    ],
)
def test_compare_recusa_antes_de_perguntar_as_notas(container, capsys, monkeypatch, quais, codigo, trecho) -> None:
    sem_terminal(monkeypatch)  # se chegasse a perguntar, falharia com outra mensagem
    v1, v2 = gerar_versoes(container)
    ids = {
        "uma": [v1],
        "repetidas": [v1, v1],
        "inexistente": [v1, "ffffffffffff"],
        "cache": [v1, gerar_versoes(container, ("v2",))[0]],
        "mesma_versao": [v1, gerar_versoes(container, ("v1",), nova=True)[0]],
    }[quais]
    assert cli(["compare", *ids], container) == codigo
    assert trecho in capsys.readouterr().err


def test_compare_sem_terminal_pede_o_arquivo_de_notas(container, capsys, monkeypatch) -> None:
    v1, v2 = gerar_versoes(container)
    sem_terminal(monkeypatch)
    assert cli(["compare", v1, v2], container) == EXIT_USAGE
    assert "--evaluations" in capsys.readouterr().err
    assert container.runs.get(v1).record.evaluation is None
    assert cli(["compare", v1, v2, "--json"], container) == EXIT_USAGE
    assert "--evaluations" in capsys.readouterr().err


def test_compare_notas_invalidas_no_arquivo_sao_recusadas_pela_api(container, capsys, tmp_path) -> None:
    v1, v2 = gerar_versoes(container)
    fora_da_escala = arquivo_de_notas(tmp_path, {v1: 4, v2: 9})
    assert cli(["compare", v1, v2, "--evaluations", fora_da_escala], container) == EXIT_USAGE
    assert "inteiro de 1 a 5" in capsys.readouterr().err
    so_um_lado = arquivo_de_notas(tmp_path, {v1: 4})
    assert cli(["compare", v1, v2, "--evaluations", so_um_lado], container) == EXIT_USAGE
    assert "não tem avaliação" in capsys.readouterr().err


# --- compare: comparação já salva (carregar ou fazer outra) -----------------------------------------------------


def test_comparacao_ja_salva_carrega_ou_faz_outra_do_zero(container, capsys, monkeypatch, tmp_path) -> None:
    # Relógio de teste: duas comparações salvas no mesmo segundo não empatam na ordem "mais recente primeiro".
    relogio = iter(range(10, 20))
    container = replace(container, comparison=replace(
        container.comparison, clock=lambda tz: datetime(2026, 11, 20, 12, next(relogio), 0, tzinfo=tz)
    ))
    v1, v2 = gerar_versoes(container)
    cli(["compare", v1, v2, "--evaluations", arquivo_de_notas(tmp_path, {v1: 2, v2: 5})], container)
    primeira = container.comparisons.list_recent()[0].record.comparison_id
    capsys.readouterr()

    # Carregar: mostra a salva, com as notas dadas antes, e não grava outra.
    responder(monkeypatch, ["x", "c"])
    assert cli(["compare", v2, v1], container) == EXIT_OK  # qualquer ordem
    saida = capsys.readouterr().out
    assert f"Já existe uma comparação destas execuções ({primeira})" in saida
    assert "Responda c (carregar) ou n (nova)." in saida and "VENCEDOR: versão v2 (v1=6 v2=15" in saida
    assert len(container.comparisons.list_recent()) == 1

    # Fazer outra: avaliação do zero, uma comparação nova; a anterior fica como estava.
    responder(monkeypatch, ["n", *RESPOSTAS_V1, "3", "a", "3", "b", "3", "c", ""])
    assert cli(["compare", v1, v2], container) == EXIT_OK
    assert "VENCEDOR: empate" in capsys.readouterr().out
    assert len(container.comparisons.list_recent()) == 2
    assert container.comparisons.get(primeira).record.winner == "v2"

    # Por flag, sem perguntar: --load mostra a mais recente.
    assert cli(["compare", v1, v2, "--load", "--json"], container) == EXIT_OK
    assert json.loads(capsys.readouterr().out)["comparison"]["winner"] is None
    sem_terminal(monkeypatch)
    assert cli(["compare", v1, v2], container) == EXIT_USAGE
    assert "--load ou --new" in capsys.readouterr().err
    assert cli(["compare", v1, v2, "--new", "--evaluations", arquivo_de_notas(tmp_path, {v1: 5, v2: 1})],
               container) == EXIT_OK
    assert len(container.comparisons.list_recent()) == 3


def test_load_e_new_sao_exclusivos() -> None:
    from app.adapters.cli.main import main

    with pytest.raises(SystemExit) as exc:
        main(["compare", "a", "b", "--load", "--new"])
    assert exc.value.code == EXIT_USAGE


# --- history comparison [list|show] ----------------------------------------------------------------------------


def test_comparison_list_paginada_e_comparison_show(container, capsys, tmp_path) -> None:
    assert cli(["history", "comparison"], container) == EXIT_OK
    assert "Nenhuma comparação encontrada." in capsys.readouterr().out
    v1, v2 = gerar_versoes(container)
    cli(["compare", v1, v2, "--evaluations", arquivo_de_notas(tmp_path, {v1: 3, v2: 5})], container)
    capsys.readouterr()
    [salva] = container.comparisons.list_recent()
    comparison_id = salva.record.comparison_id

    for argv in (["history", "comparison", "--limit", "10"], ["history", "comparison", "list", "--limit", "10"]):
        assert cli(argv, container) == EXIT_OK
        tabela = capsys.readouterr().out
        assert comparison_id in tabela and "v1=9 v2=15" in tabela and "Dona Marta" in tabela
        assert "Página 1 de 1 · 1 comparação (10 por página)" in tabela
    assert cli(["history", "comparison", "--json"], container) == EXIT_OK
    assert json.loads(capsys.readouterr().out)["items"][0]["comparison_id"] == comparison_id
    assert cli(["history", "comparison", "--limit", "3"], container) == EXIT_USAGE

    assert cli(["history", "comparison", "show", comparison_id], container) == EXIT_OK
    assert "VENCEDOR: versão v2" in capsys.readouterr().out
    assert cli(["history", "comparison", "show", comparison_id, "--json"], container) == EXIT_OK
    assert json.loads(capsys.readouterr().out)["comparison"]["comparison_id"] == comparison_id
    assert cli(["history", "comparison", "show", "aaaaaaaaaaaa"], container) == EXIT_NOT_FOUND


def test_comparison_list_nao_corta_totais_com_tres_versoes(container, capsys, tmp_path) -> None:
    v1, v2, v3 = gerar_versoes(container, ("v1", "v2", "v3"), nova=True)
    cli(["compare", v1, v2, v3, "--evaluations", arquivo_de_notas(tmp_path, {v1: 3, v2: 4, v3: 5})], container)
    capsys.readouterr()

    assert cli(["history", "comparison"], container) == EXIT_OK
    tabela = capsys.readouterr().out
    assert "v1=9 v2=12 v3=15" in tabela


# --- caminho real: módulo como subprocesso sem servidor ---------------------------------------------------------


def test_generate_compare_e_show_como_modulo_sem_servidor(tmp_path: Path) -> None:
    from tests.support import seed_prompt_versions

    catalog_dir = tmp_path / "cli-catalog"
    prompts_dir = tmp_path / "cli-prompts"
    shutil.copytree(BASE_DIR / "catalog", catalog_dir)
    shutil.copytree(BASE_DIR / "prompts", prompts_dir)
    seed_prompt_versions(prompts_dir, "v2")
    data_dir = tmp_path / "cli-var"
    env = {
        **os.environ,
        "LLM_PROVIDER": "fake",
        "DATA_DIR": str(data_dir),
        "CATALOG_DIR": str(catalog_dir),
        "PROMPTS_DIR": str(prompts_dir),
    }

    def modulo(*args: str) -> subprocess.CompletedProcess:
        # Executa o módulo CLI em subprocesso, sem stdin e sem servidor HTTP.
        return subprocess.run(
            [sys.executable, "-m", "app.adapters.cli.main", *args], cwd=BASE_DIR, capture_output=True, text=True,
            check=False, timeout=60, env=env, stdin=subprocess.DEVNULL,
        )

    ids = []
    for versao in ("v1", "v2"):
        r = modulo("generate", "--customer", "marta", "--ticket", "t-2fa", "--version", versao, "--json")
        assert r.returncode == EXIT_OK, r.stderr
        ids.append(json.loads(r.stdout)["run"]["run_id"])
    assert modulo("compare", *ids).returncode == EXIT_USAGE  # sem stdin: pede o arquivo de notas, não trava
    r = modulo("compare", *ids, "--evaluations", arquivo_de_notas(tmp_path, {ids[0]: 4, ids[1]: 4}))
    assert r.returncode == EXIT_OK, r.stderr
    assert "VENCEDOR: empate" in r.stdout
    assert len(list((data_dir / "comparisons").glob("*.json"))) == 1
