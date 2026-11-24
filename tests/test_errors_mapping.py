"""Robustez (ADR 0018 e ADR 0041): cada falha esperada vira o status HTTP certo na API e o código de saída
certo na CLI, ambos diretamente a partir das exceções do domínio."""

import pytest
from fastapi.testclient import TestClient

from app.adapters.api.main import ERROR_STATUS, create_app
from app.adapters.cli.main import ERROR_EXIT_CODES, EXIT_LLM, EXIT_NOT_FOUND, EXIT_USAGE
from app.config import Settings
from app.container import build_container
from app.domain import errors
from app.domain.errors import (
    RATE_LIMIT_MESSAGE,
    CacheReplaceRequired,
    DomainError,
    Forbidden,
    InvalidLLMOutput,
    LLMRateLimited,
    LLMUnavailable,
    NotFound,
    Unauthorized,
    ValidationFailed,
)
from app.domain.models import OUTPUT_SCHEMAS, CacheConflict, ContentType
from tests.support import LLMPorSchema, LLMRoteirizado, cli

CORPO = {"profile_id": "marta", "ticket_id": "t-2fa"}
ARGS = ["generate", "--customer", "marta", "--ticket", "t-2fa"]

# Exceção do domínio -> (status HTTP, código de saída da CLI): a tabela do ADR 0018.
TABELA = [
    (Unauthorized("x"), 401, EXIT_USAGE),
    (Forbidden("x"), 403, EXIT_USAGE),
    (NotFound("x"), 404, EXIT_NOT_FOUND),
    (ValidationFailed("x"), 422, EXIT_USAGE),
    (
        CacheReplaceRequired([CacheConflict(
            content_type=ContentType.DIAGNOSIS, prompt_version="v1", run_id="abc123def456",
        )]),
        409,
        EXIT_USAGE,
    ),
    (LLMRateLimited(RATE_LIMIT_MESSAGE), 429, EXIT_LLM),
    (InvalidLLMOutput("x"), 502, EXIT_LLM),
    (LLMUnavailable("x"), 503, EXIT_LLM),
]


def _cliente(settings: Settings, llm=None, **ajustes) -> TestClient:
    efetivo = settings.model_copy(update=ajustes) if ajustes else settings
    return TestClient(create_app(build_container(efetivo, llm=llm), frontend_dist=None))


def test_toda_excecao_do_dominio_tem_status_http_e_codigo_de_saida() -> None:
    """Guarda contra esquecer um mapeamento ao criar uma exceção nova."""
    # Compara todas as subclasses de DomainError contra as tabelas da API e CLI.
    todas = {cls for cls in vars(errors).values() if isinstance(cls, type) and issubclass(cls, DomainError)}
    todas.discard(DomainError)
    assert todas == {type(e) for e, _, _ in TABELA}
    assert set(ERROR_STATUS) == todas
    assert set(ERROR_EXIT_CODES) == todas


@pytest.mark.parametrize(("erro", "status", "_codigo"), TABELA)
def test_http_mapeia_cada_excecao_com_a_mensagem(settings: Settings, erro, status: int, _codigo: int) -> None:
    r = _cliente(settings, LLMRoteirizado(erro)).post("/api/generate", json=CORPO)
    if isinstance(erro, (LLMUnavailable, LLMRateLimited)):
        assert r.status_code == status and r.json()["detail"] == str(erro)
    else:  # NotFound, ValidationFailed e InvalidLLMOutput não saem do LLM: testados pelos casos de entrada abaixo
        assert ERROR_STATUS[type(erro)] == status


@pytest.mark.parametrize(("erro", "_status", "codigo"), TABELA)
def test_cli_mapeia_cada_excecao_para_codigo_de_saida(erro, _status: int, codigo: int) -> None:
    assert ERROR_EXIT_CODES[type(erro)] == codigo


@pytest.mark.parametrize("erro", [LLMUnavailable("fora"), LLMRateLimited(RATE_LIMIT_MESSAGE), "não é json"])
def test_cli_recebe_o_erro_do_provedor_direto_do_nucleo(settings: Settings, capsys, erro) -> None:
    respostas = (erro, erro) if isinstance(erro, str) else (erro,)  # saída inválida: tentativa e reparo
    assert cli(ARGS, build_container(settings, llm=LLMRoteirizado(*respostas))) == EXIT_LLM
    assert capsys.readouterr().err.startswith("erro: ")


def test_429_do_provedor_chega_amigavel_na_api_e_na_cli(settings: Settings, capsys) -> None:
    llm = LLMRoteirizado(LLMRateLimited(RATE_LIMIT_MESSAGE), LLMRateLimited(RATE_LIMIT_MESSAGE))
    r = _cliente(settings, llm).post("/api/generate", json=CORPO)
    assert r.status_code == 429 and r.json()["detail"] == "Limite do modelo gratuito atingido; tente em instantes."
    assert cli(ARGS, build_container(settings, llm=llm)) == EXIT_LLM
    assert RATE_LIMIT_MESSAGE in capsys.readouterr().err


def test_429_no_modo_all_com_todos_limitados_responde_429(settings: Settings) -> None:
    llm = LLMPorSchema({schema: LLMRateLimited(RATE_LIMIT_MESSAGE) for schema in OUTPUT_SCHEMAS.values()})
    r = _cliente(settings, llm).post("/api/generate", json={**CORPO, "content_type": "all"})
    assert r.status_code == 429 and r.json()["detail"] == RATE_LIMIT_MESSAGE


# --- entrada inválida ---------------------------------------------------------------------------------


def _ticket_longo(settings: Settings, texto: str) -> str:
    """Cadastra no catálogo um ticket com ``texto`` (dentro do limite atual) e devolve o id."""
    from app.services.catalog import create_ticket

    return create_ticket(build_container(settings).tickets, "Longo", texto, settings.max_ticket_chars).id


@pytest.mark.parametrize("tipo", ["diagnosis", "all"])
def test_ticket_acima_do_limite_e_422_com_mensagem_clara_sem_chamar_o_llm(settings: Settings, tipo: str) -> None:
    """O limite vale também na geração: um ticket cadastrado antes de o limite baixar é recusado sem chamar o LLM."""
    ticket_id = _ticket_longo(settings, "x" * 31)
    llm = LLMPorSchema({})
    cliente = _cliente(settings, llm, max_ticket_chars=30)
    r = cliente.post("/api/generate", json={"profile_id": "marta", "ticket_id": ticket_id, "content_type": tipo})
    assert r.status_code == 422
    assert r.json()["detail"] == "O texto do ticket tem 31 caracteres; o limite é 30."
    assert llm.chamadas == []


def test_ticket_com_acentos_conta_caracteres_e_nao_bytes(settings: Settings) -> None:
    dez, onze = _ticket_longo(settings, "ã" * 10), _ticket_longo(settings, "ã" * 11)
    cliente = _cliente(settings, max_ticket_chars=10)
    assert cliente.post("/api/generate", json={"profile_id": "marta", "ticket_id": dez}).status_code == 200
    assert cliente.post("/api/generate", json={"profile_id": "marta", "ticket_id": onze}).status_code == 422


def test_ticket_acima_do_limite_na_cli_e_codigo_1(settings: Settings, capsys) -> None:
    ticket_id = _ticket_longo(settings, "abcdef")
    pequeno = settings.model_copy(update={"max_ticket_chars": 5})
    assert cli(["generate", "--customer", "marta", "--ticket", ticket_id], build_container(pequeno)) == EXIT_USAGE
    assert "limite é 5" in capsys.readouterr().err


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


def test_ticket_ausente_e_422_do_proprio_schema(settings: Settings) -> None:
    """O ticket é sempre um do catálogo (não há mais ticket digitado): sem ``ticket_id`` o schema recusa."""
    assert _cliente(settings).post("/api/generate", json={"profile_id": "marta"}).status_code == 422


def test_corpo_sem_profile_id_e_422_do_proprio_schema(settings: Settings) -> None:
    assert _cliente(settings).post("/api/generate", json={"ticket_id": "t-2fa"}).status_code == 422


def test_api_nunca_devolve_500_para_erros_esperados(settings: Settings) -> None:
    for erro, _, _ in TABELA:
        if isinstance(erro, (LLMUnavailable, LLMRateLimited)):
            assert _cliente(settings, LLMRoteirizado(erro)).post("/api/generate", json=CORPO).status_code != 500
    assert _cliente(settings, LLMRoteirizado("{}", "{}")).post("/api/generate", json=CORPO).status_code == 502
