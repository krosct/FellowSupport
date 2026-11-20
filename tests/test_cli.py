"""Testes da CLI: chamam ``main`` direto e também o módulo como subprocesso (caminho real de uso)."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from app.adapters.cli.main import EXIT_NOT_FOUND, EXIT_OK, EXIT_USAGE, main
from app.config import BASE_DIR, Settings
from app.container import build_container


@pytest.fixture
def container(settings: Settings):
    return build_container(settings)


def test_profiles_lista_em_tabela(container, capsys) -> None:
    assert main(["profiles"], container) == EXIT_OK
    saida = capsys.readouterr().out
    for esperado in ("marta", "Dona Marta", "leigo", "didático", "telefone", "bianca", "avançado"):
        assert esperado in saida


def test_profiles_json(container, capsys) -> None:
    assert main(["profiles", "--json"], container) == EXIT_OK
    dados = json.loads(capsys.readouterr().out)
    assert {p["id"] for p in dados} == {"marta", "rafael", "bianca", "jorge"}


def test_profiles_por_id(container, capsys) -> None:
    assert main(["profiles", "--id", "jorge"], container) == EXIT_OK
    saida = capsys.readouterr().out
    assert "Seu Jorge" in saida and "marta" not in saida


def test_tickets_lista_ids_e_titulos(container, capsys) -> None:
    assert main(["tickets"], container) == EXIT_OK
    saida = capsys.readouterr().out
    assert saida.count("\n") == 5
    assert "t-2fa" in saida and "CSV exportado com acentos quebrados" in saida


def test_ticket_completo_por_id(container, capsys) -> None:
    assert main(["tickets", "--id", "t-csv"], container) == EXIT_OK
    assert "JosÃ©" in capsys.readouterr().out


def test_id_inexistente_retorna_codigo_2(container, capsys) -> None:
    assert main(["tickets", "--id", "nao-existe"], container) == EXIT_NOT_FOUND
    assert "não encontrado" in capsys.readouterr().err


def test_sem_subcomando_e_erro_de_uso(container, capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main([], container)
    assert exc.value.code == EXIT_USAGE


def test_execucao_como_modulo() -> None:
    """Executa ``python -m app.adapters.cli.main`` de verdade, como no README."""
    r = subprocess.run(
        [sys.executable, "-m", "app.adapters.cli.main", "profiles", "--json"],
        cwd=BASE_DIR, capture_output=True, text=True, check=False, timeout=30,
    )
    assert r.returncode == EXIT_OK, r.stderr
    assert len(json.loads(r.stdout)) == 4
