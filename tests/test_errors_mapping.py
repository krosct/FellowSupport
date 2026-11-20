"""Robustez (ADR 0018): cada falha esperada vira o status HTTP e o código de saída certos, com mensagem clara."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.adapters.api.main import ERROR_STATUS, create_app
from app.adapters.cli.main import ERROR_EXIT_CODES, EXIT_LLM, EXIT_NOT_FOUND, EXIT_USAGE, _exit_code, main
from app.config import Settings
from app.container import build_container
from app.domain import errors
from app.domain.errors import (
    RATE_LIMIT_MESSAGE,
    DomainError,
    InvalidLLMOutput,
    LLMRateLimited,
    LLMUnavailable,
    NotFound,
    ValidationFailed,
)
from app.domain.models import OUTPUT_SCHEMAS
from tests.support import LLMPorSchema, LLMRoteirizado

CORPO = {"profile_id": "marta", "ticket_id": "t-2fa"}
ARGS = ["generate", "--customer", "marta", "--ticket", "t-2fa"]

# Exceção do domínio -> (status HTTP, código de saída da CLI): a tabela do ADR 0018.
TABELA = [
    (NotFound("x"), 404, EXIT_NOT_FOUND),
    (ValidationFailed("x"), 422, EXIT_USAGE),
    (LLMRateLimited(RATE_LIMIT_MESSAGE), 429, EXIT_LLM),
    (InvalidLLMOutput("x"), 502, EXIT_LLM),
    (LLMUnavailable("x"), 503, EXIT_LLM),
]


def _cliente(settings: Settings, llm=None, **ajustes) -> TestClient:
    efetivo = settings.model_copy(update=ajustes) if ajustes else settings
    return TestClient(create_app(build_container(efetivo, llm=llm), frontend_dist=None))


def test_toda_excecao_do_dominio_tem_status_http_e_codigo_de_saida() -> None:
    """Guarda contra esquecer um mapeamento ao criar uma exceção nova."""
    todas = {cls for cls in vars(errors).values() if isinstance(cls, type) and issubclass(cls, DomainError)}
    todas.discard(DomainError)
    assert todas == {type(e) for e, _, _ in TABELA}
    assert set(ERROR_STATUS) == todas and set(ERROR_EXIT_CODES) == todas


@pytest.mark.parametrize(("erro", "status", "_codigo"), TABELA)
def test_http_mapeia_cada_excecao_com_a_mensagem(settings: Settings, erro, status: int, _codigo: int) -> None:
    r = _cliente(settings, LLMRoteirizado(erro)).post("/api/generate", json=CORPO)
    if isinstance(erro, (LLMUnavailable, LLMRateLimited)):
        assert r.status_code == status and r.json()["detail"] == str(erro)
    else:  # NotFound, ValidationFailed e InvalidLLMOutput não saem do LLM: testados pelos casos de entrada abaixo
        assert ERROR_STATUS[type(erro)] == status


@pytest.mark.parametrize(("erro", "_status", "codigo"), TABELA)
def test_cli_mapeia_cada_excecao(erro, _status: int, codigo: int) -> None:
    assert _exit_code(erro) == codigo
    assert ERROR_EXIT_CODES[type(erro)] == codigo


def test_429_do_provedor_chega_amigavel_na_api_e_na_cli(settings: Settings, capsys) -> None:
    llm = LLMRoteirizado(LLMRateLimited(RATE_LIMIT_MESSAGE), LLMRateLimited(RATE_LIMIT_MESSAGE))
    r = _cliente(settings, llm).post("/api/generate", json=CORPO)
    assert r.status_code == 429 and r.json()["detail"] == "Limite do modelo gratuito atingido; tente em instantes."
    assert main(ARGS, build_container(settings, llm=llm)) == EXIT_LLM
    assert RATE_LIMIT_MESSAGE in capsys.readouterr().err


def test_429_no_modo_all_com_todos_limitados_responde_429(settings: Settings) -> None:
    llm = LLMPorSchema({schema: LLMRateLimited(RATE_LIMIT_MESSAGE) for schema in OUTPUT_SCHEMAS.values()})
    r = _cliente(settings, llm).post("/api/generate", json={**CORPO, "content_type": "all"})
    assert r.status_code == 429 and r.json()["detail"] == RATE_LIMIT_MESSAGE


# --- entrada inválida ---------------------------------------------------------------------------------


@pytest.mark.parametrize("tipo", ["diagnosis", "all"])
def test_ticket_acima_do_limite_e_422_com_mensagem_clara_sem_chamar_o_llm(settings: Settings, tipo: str) -> None:
    llm = LLMPorSchema({})
    cliente = _cliente(settings, llm, max_ticket_chars=30)
    r = cliente.post("/api/generate", json={"profile_id": "marta", "ticket_text": "x" * 31, "content_type": tipo})
    assert r.status_code == 422
    assert r.json()["detail"] == "O texto do ticket tem 31 caracteres; o limite é 30."
    assert llm.chamadas == []


def test_ticket_com_acentos_conta_caracteres_e_nao_bytes(settings: Settings) -> None:
    cliente = _cliente(settings, max_ticket_chars=10)
    assert cliente.post("/api/generate", json={"profile_id": "marta", "ticket_text": "ã" * 10}).status_code == 200
    assert cliente.post("/api/generate", json={"profile_id": "marta", "ticket_text": "ã" * 11}).status_code == 422


def test_ticket_acima_do_limite_na_cli_e_codigo_1(settings: Settings, capsys) -> None:
    pequeno = settings.model_copy(update={"max_ticket_chars": 5})
    assert main(["generate", "--customer", "marta", "--text", "abcdef"], build_container(pequeno)) == EXIT_USAGE
    assert "limite é 5" in capsys.readouterr().err


@pytest.mark.parametrize("tipo", ["diagnosis", "resolution_steps", "clarifying_questions", "flow_summary", "all"])
@pytest.mark.parametrize("texto", ["", "   ", "\n\t "])
def test_ticket_livre_vazio_e_422_em_todos_os_tipos(settings: Settings, tipo: str, texto: str) -> None:
    corpo = {"profile_id": "marta", "ticket_text": texto, "content_type": tipo}
    r = _cliente(settings).post("/api/generate", json=corpo)
    assert r.status_code == 422 and "vazio" in r.json()["detail"]


@pytest.mark.parametrize("tipo", ["diagnosis", "resolution_steps", "clarifying_questions", "flow_summary", "all"])
@pytest.mark.parametrize(
    ("corpo", "trecho"),
    [
        ({"profile_id": "ninguem", "ticket_id": "t-2fa"}, "Perfil não encontrado: ninguem"),
        ({"profile_id": "marta", "ticket_id": "t-nada"}, "Ticket não encontrado: t-nada"),
        ({"profile_id": "marta", "ticket_id": "t-2fa", "prompt_version": "v99"}, "v99"),
    ],
)
def test_id_ou_versao_inexistente_e_404_em_todos_os_tipos(
    settings: Settings, tipo: str, corpo: dict, trecho: str
) -> None:
    llm = LLMPorSchema({})
    r = _cliente(settings, llm).post("/api/generate", json={**corpo, "content_type": tipo})
    assert r.status_code == 404 and trecho in r.json()["detail"]
    assert llm.chamadas == []


@pytest.mark.parametrize(
    "corpo", [{"profile_id": "marta"}, {"profile_id": "marta", "ticket_id": "t-2fa", "ticket_text": "x"}]
)
def test_ticket_ausente_ou_duplicado_e_422(settings: Settings, corpo: dict) -> None:
    assert _cliente(settings).post("/api/generate", json=corpo).status_code == 422


def test_corpo_sem_profile_id_e_422_do_proprio_schema(settings: Settings) -> None:
    assert _cliente(settings).post("/api/generate", json={"ticket_id": "t-2fa"}).status_code == 422


def test_api_nunca_devolve_500_para_erros_esperados(settings: Settings) -> None:
    for erro, _, _ in TABELA:
        if isinstance(erro, (LLMUnavailable, LLMRateLimited)):
            assert _cliente(settings, LLMRoteirizado(erro)).post("/api/generate", json=CORPO).status_code != 500
    assert _cliente(settings, LLMRoteirizado("{}", "{}")).post("/api/generate", json=CORPO).status_code == 502
