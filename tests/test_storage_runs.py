"""Testes da persistência de execuções: um arquivo por execução, escrita atômica e caminho exibido (ADR 0009)."""

import json
from pathlib import Path

import pytest

from app.adapters.storage import json_files
from app.adapters.storage.json_files import JsonRunRepo, atomic_write_json, display_path
from app.config import BASE_DIR
from app.domain.errors import NotFound
from app.domain.models import RunRecord


def test_grava_em_runs_data_e_arquivo_com_carimbo_e_id(tmp_path: Path, make_record) -> None:
    caminho = Path(JsonRunRepo(tmp_path).save(make_record()))
    assert caminho == tmp_path / "runs" / "2026-11-20" / "20261120T140311_abc123def456.json"
    assert caminho.is_file()


def test_arquivo_salvo_valida_de_volta_e_preserva_acentos(tmp_path: Path, make_record) -> None:
    registro = make_record(ticket={"id": "t-acesso", "title": "Não acesso", "text": "não é possível acessar"})
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
    # Simula erro no os.replace para garantir atomicidade ao salvar uma execução.
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


# --- leitura: get e iter_recent -----------------------------------------------------------------------


def test_get_devolve_o_registro_e_o_caminho(tmp_path: Path, make_record) -> None:
    repo = JsonRunRepo(tmp_path)
    registro = make_record(run_id="aaaaaaaaaaaa")
    caminho = repo.save(registro)
    guardado = repo.get("aaaaaaaaaaaa")
    assert guardado.record == registro and guardado.saved_path == caminho


@pytest.mark.parametrize(
    "run_id", ["nao-existe", "bbbbbbbbbbbb", "*", "../x", "aaaaaaaaaaaa/../..", "AAAAAAAAAAAA", ""]
)
def test_get_com_id_inexistente_ou_malformado_e_not_found(tmp_path: Path, make_record, run_id: str) -> None:
    repo = JsonRunRepo(tmp_path)
    repo.save(make_record(run_id="aaaaaaaaaaaa"))
    with pytest.raises(NotFound):
        repo.get(run_id)


def test_get_de_arquivo_corrompido_e_not_found(tmp_path: Path, make_record) -> None:
    repo = JsonRunRepo(tmp_path)
    Path(repo.save(make_record(run_id="aaaaaaaaaaaa"))).write_text("{ não é json", encoding="utf-8")
    with pytest.raises(NotFound, match="ilegível"):
        repo.get("aaaaaaaaaaaa")


def test_iter_recent_ordena_do_mais_novo_para_o_mais_antigo(tmp_path: Path, make_record) -> None:
    repo = JsonRunRepo(tmp_path)
    repo.save(make_record(run_id="aaaaaaaaaaaa", timestamp="2026-11-19T10:00:00-03:00"))
    repo.save(make_record(run_id="bbbbbbbbbbbb", timestamp="2026-11-20T09:00:00-03:00"))
    repo.save(make_record(run_id="cccccccccccc", timestamp="2026-11-20T14:00:00-03:00"))
    assert [s.record.run_id for s in repo.iter_recent()] == ["cccccccccccc", "bbbbbbbbbbbb", "aaaaaaaaaaaa"]


def test_iter_recent_desempata_o_mesmo_segundo_pela_ordem_de_gravacao(tmp_path: Path, make_record) -> None:
    repo = JsonRunRepo(tmp_path)
    # Ids em ordem alfabética inversa à de gravação: o desempate não pode ser pelo id.
    for run_id in ("ffffffffffff", "eeeeeeeeeeee", "dddddddddddd"):
        repo.save(make_record(run_id=run_id))
    assert [s.record.run_id for s in repo.iter_recent()] == ["dddddddddddd", "eeeeeeeeeeee", "ffffffffffff"]


def test_iter_recent_pula_arquivo_ilegivel_e_sem_pasta_devolve_vazio(tmp_path: Path, make_record) -> None:
    repo = JsonRunRepo(tmp_path)
    assert list(repo.iter_recent()) == []
    Path(repo.save(make_record(run_id="aaaaaaaaaaaa"))).write_text("lixo", encoding="utf-8")
    repo.save(make_record(run_id="bbbbbbbbbbbb", timestamp="2026-11-20T15:00:00-03:00"))
    assert [s.record.run_id for s in repo.iter_recent()] == ["bbbbbbbbbbbb"]


def test_regravar_a_mesma_execucao_substitui_o_arquivo_sem_criar_outro(tmp_path: Path, make_record) -> None:
    """A avaliação reusa ``save``: mesmo ``run_id`` e ``timestamp`` caem no mesmo caminho (troca atômica)."""
    repo = JsonRunRepo(tmp_path)
    original = make_record()
    primeiro = repo.save(original)
    segundo = repo.save(original.model_copy(update={"evaluation": {"evaluator": "candidato"}}))
    assert primeiro == segundo
    assert len(list((tmp_path / "runs").rglob("*.json"))) == 1
    assert repo.get("abc123def456").record.evaluation == {"evaluator": "candidato"}
