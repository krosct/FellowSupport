"""Testes da persistência de execuções: um arquivo por execução, escrita atômica e caminho exibido (ADR 0009)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.adapters.storage import json_files
from app.adapters.storage.json_files import JsonRunRepo, atomic_write_json, display_path
from app.config import BASE_DIR
from app.domain.models import RunRecord


def test_grava_em_runs_data_e_arquivo_com_carimbo_e_id(tmp_path: Path, make_record) -> None:
    caminho = Path(JsonRunRepo(tmp_path).save(make_record()))
    assert caminho == tmp_path / "runs" / "2026-11-20" / "20261120T140311_abc123def456.json"
    assert caminho.is_file()


def test_arquivo_salvo_valida_de_volta_e_preserva_acentos(tmp_path: Path, make_record) -> None:
    registro = make_record(ticket={"id": None, "title": "Ticket digitado", "text": "não é possível acessar"})
    caminho = Path(JsonRunRepo(tmp_path).save(registro))
    bruto = caminho.read_text(encoding="utf-8")
    assert "não é possível acessar" in bruto  # ensure_ascii=False
    assert RunRecord.model_validate(json.loads(bruto)) == registro


def test_duas_execucoes_geram_dois_arquivos(tmp_path: Path, make_record) -> None:
    repo = JsonRunRepo(tmp_path)
    repo.save(make_record(run_id="aaaaaaaaaaaa"))
    repo.save(make_record(run_id="bbbbbbbbbbbb"))
    assert len(list((tmp_path / "runs" / "2026-11-20").glob("*.json"))) == 2


def test_pasta_do_dia_segue_o_fuso_do_timestamp(tmp_path: Path, make_record) -> None:
    """23h30 em Brasília é o dia seguinte em UTC; a pasta deve usar a data local do registro."""
    caminho = Path(JsonRunRepo(tmp_path).save(make_record(timestamp="2026-11-20T23:30:00-03:00")))
    assert caminho.parent.name == "2026-11-20"


def test_escrita_atomica_nao_deixa_temporario_nem_corrompe_o_anterior(tmp_path: Path, monkeypatch) -> None:
    alvo = tmp_path / "x.json"
    atomic_write_json(alvo, {"v": 1})

    def falha(*_a, **_k):
        raise OSError("disco cheio")

    monkeypatch.setattr(json_files.os, "replace", falha)
    with pytest.raises(OSError):
        atomic_write_json(alvo, {"v": 2})
    assert json.loads(alvo.read_text(encoding="utf-8")) == {"v": 1}
    assert [p.name for p in tmp_path.iterdir()] == ["x.json"]


def test_display_path_e_relativo_dentro_do_repositorio_e_absoluto_fora() -> None:
    assert display_path(BASE_DIR / "var" / "runs" / "a.json") == "var/runs/a.json"
    assert display_path(Path("/tmp/outro/a.json")) == "/tmp/outro/a.json"
