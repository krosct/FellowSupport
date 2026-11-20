"""Testes da CLI: chamam ``main`` direto e também o módulo como subprocesso (caminho real de uso)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.adapters.cli.main import EXIT_LLM, EXIT_NOT_FOUND, EXIT_OK, EXIT_USAGE, main
from app.config import BASE_DIR, Settings
from app.container import build_container
from app.domain.errors import LLMRateLimited, LLMUnavailable
from app.domain.models import Diagnosis
from tests.support import LLMPorSchema, LLMRoteirizado


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


# --- versions e generate -----------------------------------------------------------------------------


def _salvos(settings: Settings) -> list[Path]:
    return sorted((settings.data_dir / "runs").rglob("*.json"))


def test_versions_lista_a_v1_como_padrao(container, capsys) -> None:
    assert main(["versions"], container) == EXIT_OK
    saida = capsys.readouterr().out
    assert "v1" in saida and "(padrão)" in saida and "Linha de base" in saida


def test_versions_json(container, capsys) -> None:
    assert main(["versions", "--json"], container) == EXIT_OK
    [v1] = json.loads(capsys.readouterr().out)
    assert v1["version"] == "v1" and v1["is_default"] is True and len(v1["content_sha256"]) == 64


def test_generate_mostra_saida_legivel_e_o_caminho_do_json(container, settings, capsys) -> None:
    assert main(["generate", "--customer", "marta", "--ticket", "t-2fa"], container) == EXIT_OK
    saida = capsys.readouterr().out
    for esperado in ("Dona Marta", "Código de verificação", "v1", "fake-llm", "HIPÓTESES", "EVIDÊNCIAS DISPONÍVEIS",
                     "INFORMAÇÕES FALTANTES", "CONCLUSÃO PROVÁVEL", "RESUMO PARA O CLIENTE"):
        assert esperado in saida
    [arquivo] = _salvos(settings)
    assert f"JSON salvo em: {arquivo}" in saida
    salvo = json.loads(arquivo.read_text(encoding="utf-8"))
    assert salvo["status"] == "ok" and salvo["customer_id"] == "marta" and salvo["prompt_version"] == "v1"
    Diagnosis.model_validate(salvo["output"])


# Cabeçalhos de seção que cada tipo imprime (saída legível, não JSON).
SECOES = {
    "diagnosis": ["HIPÓTESES", "CONCLUSÃO PROVÁVEL"],
    "resolution_steps": ["ABERTURA", "PASSOS", "Esperado:", "Se falhar:", "QUANDO ESCALAR", "FECHAMENTO"],
    "clarifying_questions": ["PERGUNTAS", "Motivo:", "Destrava:", "DÁ PARA AVANÇAR SEM AS RESPOSTAS? SIM"],
    "flow_summary": ["(INÍCIO)", "├─ Sim ─▶", "└─ Não ─▶", "FIM:"],
}


@pytest.mark.parametrize("tipo", list(SECOES))
def test_generate_imprime_cada_tipo_de_forma_legivel(container, settings, capsys, tipo) -> None:
    assert main(["generate", "--customer", "marta", "--ticket", "t-2fa", "--type", tipo], container) == EXIT_OK
    saida = capsys.readouterr().out
    for trecho in SECOES[tipo]:
        assert trecho in saida
    [arquivo] = _salvos(settings)
    assert json.loads(arquivo.read_text(encoding="utf-8"))["content_type"] == tipo


def test_fluxo_na_cli_imprime_exatamente_o_ascii_gravado(container, settings, capsys) -> None:
    main(["generate", "--customer", "bianca", "--ticket", "t-sync", "--type", "flow_summary"], container)
    saida = capsys.readouterr().out
    gravado = json.loads(_salvos(settings)[0].read_text(encoding="utf-8"))["rendered"]
    assert gravado in saida


def test_generate_com_texto_livre(container, settings, capsys) -> None:
    assert main(["generate", "--customer", "bianca", "--text", "A API devolve 500."], container) == EXIT_OK
    assert "Ticket digitado" in capsys.readouterr().out
    assert json.loads(_salvos(settings)[0].read_text(encoding="utf-8"))["ticket"]["id"] is None


def test_generate_json(container, capsys) -> None:
    assert main(["generate", "--customer", "rafael", "--ticket", "t-csv", "--json"], container) == EXIT_OK
    dados = json.loads(capsys.readouterr().out)
    assert dados["run"]["customer_id"] == "rafael" and dados["saved_path"].endswith(".json")


@pytest.mark.parametrize(
    ("argv", "codigo", "trecho"),
    [
        (["generate", "--customer", "x", "--ticket", "t-2fa"], EXIT_NOT_FOUND, "Perfil não encontrado"),
        (["generate", "--customer", "marta", "--ticket", "x"], EXIT_NOT_FOUND, "Ticket não encontrado"),
        (["generate", "--customer", "marta", "--ticket", "t-2fa", "--version", "v9"], EXIT_NOT_FOUND, "v9"),
        (["generate", "--customer", "marta", "--text", "  "], EXIT_USAGE, "vazio"),
    ],
)
def test_generate_erros_de_entrada(container, settings, capsys, argv, codigo, trecho) -> None:
    assert main(argv, container) == codigo
    assert trecho in capsys.readouterr().err
    assert _salvos(settings) == []


@pytest.mark.parametrize("argv", [
    ["generate", "--customer", "marta"],
    ["generate", "--ticket", "t-2fa"],
    ["generate", "--customer", "marta", "--ticket", "t-2fa", "--text", "x"],
    ["generate", "--customer", "marta", "--ticket", "t-2fa", "--type", "poema"],
])
def test_generate_argumentos_invalidos_sao_erro_de_uso(container, argv) -> None:
    with pytest.raises(SystemExit) as exc:
        main(argv, container)
    assert exc.value.code == EXIT_USAGE


@pytest.mark.parametrize("erro", [LLMUnavailable("fora do ar"), LLMRateLimited("muitas")])
def test_generate_erro_do_provedor_retorna_codigo_3_e_grava_a_execucao(settings, capsys, erro) -> None:
    container = build_container(settings, llm=LLMRoteirizado(erro))
    assert main(["generate", "--customer", "marta", "--ticket", "t-2fa"], container) == EXIT_LLM
    assert str(erro) in capsys.readouterr().err
    assert json.loads(_salvos(settings)[0].read_text(encoding="utf-8"))["status"] == "error"


def test_generate_saida_invalida_apos_reparo_retorna_codigo_3(settings, capsys) -> None:
    container = build_container(settings, llm=LLMRoteirizado("{}", "{}"))
    assert main(["generate", "--customer", "marta", "--ticket", "t-2fa"], container) == EXIT_LLM
    assert "reparo" in capsys.readouterr().err


def test_generate_como_modulo_com_fake(tmp_path) -> None:
    """Caminho real de uso: subprocesso, provedor fake forçado por ambiente (ignora o .env do autor)."""
    ambiente = {**os.environ, "LLM_PROVIDER": "fake", "DATA_DIR": str(tmp_path)}
    r = subprocess.run(
        [sys.executable, "-m", "app.adapters.cli.main", "generate", "--customer", "jorge", "--ticket", "t-sync"],
        cwd=BASE_DIR, capture_output=True, text=True, check=False, timeout=60, env=ambiente,
    )
    assert r.returncode == EXIT_OK, r.stderr
    assert "JSON salvo em:" in r.stdout
    [arquivo] = list(tmp_path.rglob("*.json"))
    assert json.loads(arquivo.read_text(encoding="utf-8"))["provider"] == "fake"


# --- generate --type all ----------------------------------------------------------------------------


def test_generate_all_imprime_os_quatro_tipos_e_um_json_por_tipo(container, settings, capsys) -> None:
    assert main(["generate", "--customer", "marta", "--ticket", "t-2fa", "--type", "all"], container) == EXIT_OK
    saida = capsys.readouterr().out
    for titulo in ("DIAGNÓSTICO", "PASSO A PASSO", "PERGUNTAS DE ESCLARECIMENTO", "RESUMO VISUAL DO FLUXO"):
        assert titulo in saida
    for trecho in ("HIPÓTESES", "PASSOS", "DÁ PARA AVANÇAR", "├─ Sim ─▶"):
        assert trecho in saida
    salvos = _salvos(settings)
    assert len(salvos) == 4 and all(str(a) in saida for a in salvos)


def test_generate_all_json(container, capsys) -> None:
    argv = ["generate", "--customer", "rafael", "--ticket", "t-csv", "--type", "all", "--json"]
    assert main(argv, container) == EXIT_OK
    itens = json.loads(capsys.readouterr().out)["results"]
    assert [i["content_type"] for i in itens] == [
        "diagnosis", "resolution_steps", "clarifying_questions", "flow_summary",
    ]
    assert all(i["error"] is None and i["saved_path"].endswith(".json") for i in itens)


def test_generate_all_com_falha_parcial_imprime_o_resto_e_sai_com_codigo_do_provedor(settings, capsys) -> None:
    from app.domain.models import ResolutionSteps

    llm = LLMPorSchema({ResolutionSteps: LLMUnavailable("fora do ar")})
    codigo = main(["generate", "--customer", "marta", "--ticket", "t-2fa", "--type", "all"],
                  build_container(settings, llm=llm))
    saida, erro = capsys.readouterr()
    assert codigo == EXIT_LLM and "fora do ar" in erro
    assert "HIPÓTESES" in saida and "├─ Sim ─▶" in saida  # os outros tipos saíram
    assert "FALHOU: fora do ar" in saida and "JSON de erro salvo em" in saida
    assert len(_salvos(settings)) == 4


def test_generate_all_com_entrada_invalida_nao_gera(container, settings, capsys) -> None:
    assert main(["generate", "--customer", "x", "--ticket", "t-2fa", "--type", "all"], container) == EXIT_NOT_FOUND
    assert _salvos(settings) == []
