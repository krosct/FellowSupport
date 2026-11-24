"""Testes do ``CacheStore`` em JSON: ponteiro para a execução de origem, escrita atômica e tolerância a lixo."""

import json
from pathlib import Path

import pytest

from app.adapters.storage import json_files
from app.adapters.storage.json_files import JsonCacheStore
from app.domain.errors import ValidationFailed
from app.domain.models import CacheEntry

CHAVE = "a" * 64


def _entrada(chave: str = CHAVE, origem: str = "aaaaaaaaaaaa") -> CacheEntry:
    return CacheEntry(cache_key=chave, source_run_id=origem, created_at="2026-11-20T14:03:11-03:00")


def test_grava_em_cache_chave_json_apontando_para_a_origem(tmp_path: Path) -> None:
    JsonCacheStore(tmp_path).put(_entrada())
    arquivo = tmp_path / "cache" / f"{CHAVE}.json"
    assert json.loads(arquivo.read_text(encoding="utf-8")) == {
        "cache_key": CHAVE, "source_run_id": "aaaaaaaaaaaa", "created_at": "2026-11-20T14:03:11-03:00",
    }


def test_get_devolve_a_entrada_gravada(tmp_path: Path) -> None:
    cache = JsonCacheStore(tmp_path)
    cache.put(_entrada())
    assert cache.get(CHAVE) == _entrada()


def test_get_de_chave_inexistente_ou_malformada_devolve_none(tmp_path: Path) -> None:
    cache = JsonCacheStore(tmp_path)
    assert cache.get(CHAVE) is None
    for malformada in ("", "x", "../x", "*", "A" * 64, "a" * 63):
        assert cache.get(malformada) is None


def test_put_substitui_a_entrada_da_mesma_chave(tmp_path: Path) -> None:
    # Sobrescreve o ponteiro da chave existente sem deixar arquivos temporários.
    cache = JsonCacheStore(tmp_path)
    cache.put(_entrada(origem="aaaaaaaaaaaa"))
    cache.put(_entrada(origem="bbbbbbbbbbbb"))
    entrada = cache.get(CHAVE)
    assert entrada is not None and entrada.source_run_id == "bbbbbbbbbbbb"
    assert [p.name for p in (tmp_path / "cache").iterdir()] == [f"{CHAVE}.json"]  # sem temporários


def test_arquivo_corrompido_ou_de_outra_chave_vale_como_ausente(tmp_path: Path) -> None:
    cache = JsonCacheStore(tmp_path)
    pasta = tmp_path / "cache"
    pasta.mkdir()
    (pasta / f"{CHAVE}.json").write_text("{ quebrado", encoding="utf-8")
    assert cache.get(CHAVE) is None
    outra = "b" * 64
    (pasta / f"{outra}.json").write_text(_entrada(chave=CHAVE).model_dump_json(), encoding="utf-8")
    assert cache.get(outra) is None  # arquivo copiado à mão não responde por outra chave


def test_put_com_chave_malformada_e_recusado(tmp_path: Path) -> None:
    with pytest.raises(ValidationFailed):
        JsonCacheStore(tmp_path).put(_entrada(chave="../fuga"))
    assert not (tmp_path / "cache").exists()


def test_escrita_do_cache_e_atomica(tmp_path: Path, monkeypatch) -> None:
    # Simula erro no os.replace para confirmar que o cache anterior não é corrompido.
    cache = JsonCacheStore(tmp_path)
    cache.put(_entrada(origem="aaaaaaaaaaaa"))

    def falha(*_a, **_k):
        raise OSError("disco cheio")

    monkeypatch.setattr(json_files.os, "replace", falha)
    with pytest.raises(OSError):
        cache.put(_entrada(origem="bbbbbbbbbbbb"))
    entrada = cache.get(CHAVE)
    assert entrada is not None and entrada.source_run_id == "aaaaaaaaaaaa"  # o anterior segue íntegro
    assert [p.name for p in (tmp_path / "cache").iterdir()] == [f"{CHAVE}.json"]
