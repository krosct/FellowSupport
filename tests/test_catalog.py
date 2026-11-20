"""Testes do catálogo e dos repositórios JSON (itens 4.1 e 10 do PDF)."""

from __future__ import annotations

import json

import pytest

from app.adapters.storage.json_files import (
    JsonProfileRepo,
    JsonTicketRepo,
    atomic_write_json,
)
from app.config import Settings
from app.domain.errors import NotFound, ValidationFailed
from app.domain.models import Channel, CommStyle, TechLevel


def test_catalogo_tem_de_3_a_5_perfis_com_enums_validos(settings: Settings) -> None:
    perfis = JsonProfileRepo(settings.catalog_dir).list_all()
    assert 3 <= len(perfis) <= 5
    for p in perfis:
        assert isinstance(p.tech_level, TechLevel)
        assert isinstance(p.comm_style, CommStyle)
        assert isinstance(p.channel, Channel)


def test_perfis_do_catalogo_contrastam(settings: Settings) -> None:
    por_id = {p.id: p for p in JsonProfileRepo(settings.catalog_dir).list_all()}
    assert (por_id["marta"].tech_level, por_id["marta"].comm_style, por_id["marta"].channel) == (
        "leigo", "didático", "telefone")
    assert (por_id["rafael"].tech_level, por_id["rafael"].channel) == ("intermediário", "e-mail")
    assert (por_id["bianca"].tech_level, por_id["bianca"].comm_style) == ("avançado", "direto")
    assert (por_id["jorge"].tech_level, por_id["jorge"].channel) == ("leigo", "chat")


def test_catalogo_tem_5_tickets_realistas(settings: Settings) -> None:
    tickets = JsonTicketRepo(settings.catalog_dir).list_all()
    assert len(tickets) == 5
    for t in tickets:
        assert len(t.text) > 300  # relatos com sinais, evidências e lacunas
    assert {t.id for t in tickets} == {"t-2fa", "t-sync", "t-webhook", "t-dashboard", "t-csv"}


def test_get_inexistente_levanta_not_found(settings: Settings) -> None:
    with pytest.raises(NotFound):
        JsonProfileRepo(settings.catalog_dir).get("nao-existe")
    with pytest.raises(NotFound):
        JsonTicketRepo(settings.catalog_dir).get("nao-existe")


def test_catalogo_invalido_levanta_validation_failed(tmp_path) -> None:
    (tmp_path / "profiles.json").write_text(
        json.dumps(
            [{"id": "x", "name": "X", "tech_level": "mago", "comm_style": "direto", "channel": "chat"}]
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValidationFailed):
        JsonProfileRepo(tmp_path).list_all()
    with pytest.raises(ValidationFailed):  # arquivo ausente
        JsonTicketRepo(tmp_path).list_all()


def test_ids_duplicados_sao_rejeitados(tmp_path) -> None:
    item = {"id": "a", "title": "t", "text": "x"}
    (tmp_path / "tickets.json").write_text(json.dumps([item, item]), encoding="utf-8")
    with pytest.raises(ValidationFailed):
        JsonTicketRepo(tmp_path).list_all()


def test_escrita_atomica_nao_deixa_temporarios(tmp_path) -> None:
    destino = tmp_path / "sub" / "dado.json"
    atomic_write_json(destino, {"nome": "Conceição"})
    assert json.loads(destino.read_text(encoding="utf-8")) == {"nome": "Conceição"}
    assert "Conceição" in destino.read_text(encoding="utf-8")  # acentos legíveis
    assert [p.name for p in destino.parent.iterdir()] == ["dado.json"]


def test_escrita_atomica_preserva_arquivo_anterior_em_falha(tmp_path) -> None:
    destino = tmp_path / "dado.json"
    atomic_write_json(destino, {"v": 1})
    with pytest.raises(TypeError):
        atomic_write_json(destino, {"v": object()})  # não serializável
    assert json.loads(destino.read_text(encoding="utf-8")) == {"v": 1}
    assert [p.name for p in tmp_path.iterdir()] == ["dado.json"]
