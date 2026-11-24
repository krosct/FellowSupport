"""Testes da CLI (adaptador direto do núcleo, ADR 0041): ``cli`` roda a CLI contra um ``Container`` em memória e os
testes de subprocesso rodam o módulo diretamente com ``LLM_PROVIDER=fake`` e pastas temporárias, sem servidor HTTP."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from app.adapters.cli.main import EXIT_LLM, EXIT_NOT_FOUND, EXIT_OK, EXIT_USAGE, main
from app.config import BASE_DIR, Settings
from app.container import build_container
from app.domain.errors import LLMRateLimited, LLMUnavailable
from app.domain.models import Diagnosis
from tests.support import LATEST_VERSION, LLMPorSchema, LLMRoteirizado, cli


@pytest.fixture
def container(settings: Settings):
    return build_container(settings)


def test_profile_list_em_tabela(container, capsys) -> None:
    assert cli(["profile", "list"], container) == EXIT_OK
    saida = capsys.readouterr().out
    linhas = saida.splitlines()
    assert linhas[0].split() == ["ID", "NOME", "NÍVEL", "ESTILO", "CANAL"]
    for esperado in ("marta", "Dona Marta", "leigo", "didático", "telefone", "bianca", "avançado", "amanda", "Amanda"):
        assert esperado in saida


def test_profile_list_json(container, capsys) -> None:
    assert cli(["profile", "list", "--json"], container) == EXIT_OK
    dados = json.loads(capsys.readouterr().out)
    assert {p["id"] for p in dados} == {"marta", "rafael", "bianca", "jorge", "amanda"}


def test_profile_list_por_id(container, capsys) -> None:
    assert cli(["profile", "list", "--id", "jorge"], container) == EXIT_OK
    saida = capsys.readouterr().out
    assert "Seu Jorge" in saida and "marta" not in saida


def test_ticket_list_ids_e_titulos(container, capsys) -> None:
    assert cli(["ticket", "list"], container) == EXIT_OK
    saida = capsys.readouterr().out
    linhas = saida.splitlines()
    assert linhas[0].split() == ["ID", "TÍTULO"]
    assert len(linhas) == 1 + len(container.tickets.list_all())
    assert "t-2fa" in saida and "t-webhook" in saida


def test_ticket_list_completo_por_id(container, capsys) -> None:
    assert cli(["ticket", "list", "--id", "t-webhook"], container) == EXIT_OK
    assert "POST /v2/punches" in capsys.readouterr().out


def test_id_inexistente_retorna_codigo_2(container, capsys) -> None:
    assert cli(["ticket", "list", "--id", "nao-existe"], container) == EXIT_NOT_FOUND
    assert "não encontrado" in capsys.readouterr().err


def test_sem_subcomando_e_erro_de_uso(container, capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == EXIT_USAGE


@pytest.mark.parametrize("comando_antigo", ["profiles", "tickets", "comparisons", "comparison", "versions"])
def test_comandos_no_plural_foram_removidos(comando_antigo: str) -> None:
    with pytest.raises(SystemExit) as exc:
        main([comando_antigo])
    assert exc.value.code == EXIT_USAGE


def test_history_sem_subcomando_e_generations_plural_sao_erro_de_uso() -> None:
    for argv in (["history"], ["history", "generations"]):
        with pytest.raises(SystemExit) as exc:
            main(argv)
        assert exc.value.code == EXIT_USAGE


def _cli_env(tmp_path: Path) -> tuple[dict[str, str], Path]:
    """Ambiente isolado para rodar a CLI em subprocesso sem tocar em ``catalog/`` nem ``var/``."""
    catalog_dir = tmp_path / "cli-catalog"
    shutil.copytree(BASE_DIR / "catalog", catalog_dir)
    data_dir = tmp_path / "cli-var"
    env = {
        **os.environ,
        "LLM_PROVIDER": "fake",
        "DATA_DIR": str(data_dir),
        "CATALOG_DIR": str(catalog_dir),
    }
    return env, data_dir


def _modulo(env: dict[str, str], *args: str) -> subprocess.CompletedProcess:
    """Executa ``python -m app.adapters.cli.main`` diretamente em subprocesso, sem servidor HTTP e sem stdin."""
    return subprocess.run(
        [sys.executable, "-m", "app.adapters.cli.main", *args], cwd=BASE_DIR, capture_output=True, text=True,
        check=False, timeout=60, env=env, stdin=subprocess.DEVNULL,
    )


def test_execucao_como_modulo_sem_servidor(tmp_path: Path) -> None:
    env, _ = _cli_env(tmp_path)
    r = _modulo(env, "profile", "list", "--json")
    assert r.returncode == EXIT_OK, r.stderr
    assert len(json.loads(r.stdout)) == 5


# --- prompt list e generate --------------------------------------------------------------------------


def _salvos(settings: Settings) -> list[Path]:
    # Lista os JSONs de execução salvos na pasta temporária do teste.
    return sorted((settings.data_dir / "runs").rglob("*.json"))


def test_prompt_list_marca_a_mais_nova_como_padrao(settings, capsys) -> None:
    from tests.support import seed_prompt_versions

    seed_prompt_versions(settings.prompts_dir, "v2", "v3")
    container = build_container(settings)
    assert cli(["prompt", "list"], container) == EXIT_OK
    saida = capsys.readouterr().out
    assert "O que mudou" not in saida
    linhas = {linha.split()[0]: linha for linha in saida.splitlines()[1:]}
    assert "(padrão)" in linhas[LATEST_VERSION] and "(padrão)" not in linhas["v1"] and "Linha de base" in linhas["v1"]


def test_prompt_list_details_mostra_o_que_mudou(settings, capsys) -> None:
    from tests.support import seed_prompt_versions

    seed_prompt_versions(settings.prompts_dir, "v2", "v3")
    container = build_container(settings)
    assert cli(["prompt", "list", "--details"], container) == EXIT_OK
    tabela, mudancas = capsys.readouterr().out.split("\n\n", 1)
    linhas = {linha.split()[0]: linha for linha in tabela.splitlines()[1:]}
    assert "(padrão)" in linhas[LATEST_VERSION] and "Linha de base" in linhas["v1"]
    # O que mudou em cada versão derivada, como na aba Comparar do site (a v1 é a base e não aparece).
    assert "O que mudou na v2 em relação à v1" in mudancas and "O que mudou na v3 em relação à v2" in mudancas
    assert "Por quê:" in mudancas and "Efeito esperado:" in mudancas and "na v1 em" not in mudancas


def test_prompt_list_json(settings, capsys) -> None:
    from tests.support import seed_prompt_versions

    seed_prompt_versions(settings.prompts_dir, "v2", "v3")
    container = build_container(settings)
    assert cli(["prompt", "list", "--json"], container) == EXIT_OK
    itens = json.loads(capsys.readouterr().out)
    assert len(itens) >= 3
    v1, v2, ultima = itens[0], itens[1], itens[-1]
    assert v1["version"] == "v1" and v1["is_default"] is False and len(v1["content_sha256"]) == 64
    assert v2["version"] == "v2" and v2["based_on"] == "v1"
    assert all(not item["is_default"] for item in itens[:-1])
    assert ultima["version"] == LATEST_VERSION and ultima["is_default"] is True


def test_generate_mostra_saida_legivel_e_o_caminho_do_json(container, settings, capsys) -> None:
    assert cli(["generate", "--customer", "marta", "--ticket", "t-2fa"], container) == EXIT_OK
    saida = capsys.readouterr().out
    for esperado in ("Dona Marta", "Código de verificação", LATEST_VERSION, "fake-llm", "HIPÓTESES",
                     "EVIDÊNCIAS DISPONÍVEIS", "INFORMAÇÕES FALTANTES", "CONCLUSÃO PROVÁVEL", "RESUMO PARA O CLIENTE"):
        assert esperado in saida
    [arquivo] = _salvos(settings)
    assert f"JSON salvo em: {arquivo}" in saida
    salvo = json.loads(arquivo.read_text(encoding="utf-8"))
    assert salvo["status"] == "ok" and salvo["customer_id"] == "marta" and salvo["prompt_version"] == LATEST_VERSION
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
    assert cli(["generate", "--customer", "marta", "--ticket", "t-2fa", "--type", tipo], container) == EXIT_OK
    saida = capsys.readouterr().out
    for trecho in SECOES[tipo]:
        assert trecho in saida
    [arquivo] = _salvos(settings)
    assert json.loads(arquivo.read_text(encoding="utf-8"))["content_type"] == tipo


def test_fluxo_na_cli_imprime_exatamente_o_ascii_gravado(container, settings, capsys) -> None:
    cli(["generate", "--customer", "bianca", "--ticket", "t-webhook", "--type", "flow_summary"], container)
    saida = capsys.readouterr().out
    gravado = json.loads(_salvos(settings)[0].read_text(encoding="utf-8"))["rendered"]
    assert gravado in saida


def test_generate_json(container, capsys) -> None:
    assert cli(["generate", "--customer", "rafael", "--ticket", "t-webhook", "--json"], container) == EXIT_OK
    dados = json.loads(capsys.readouterr().out)
    assert dados["run"]["customer_id"] == "rafael" and dados["saved_path"].endswith(".json")


@pytest.mark.parametrize(
    ("argv", "codigo", "trecho"),
    [
        (["generate", "--customer", "x", "--ticket", "t-2fa"], EXIT_NOT_FOUND, "Perfil não encontrado"),
        (["generate", "--customer", "marta", "--ticket", "x"], EXIT_NOT_FOUND, "Ticket não encontrado"),
        (["generate", "--customer", "marta", "--ticket", "t-2fa", "--version", "v9"], EXIT_NOT_FOUND, "v9"),
    ],
)
def test_generate_erros_de_entrada(container, settings, capsys, argv, codigo, trecho) -> None:
    assert cli(argv, container) == codigo
    assert trecho in capsys.readouterr().err
    assert _salvos(settings) == []


@pytest.mark.parametrize("argv", [
    ["generate", "--customer", "marta"],
    ["generate", "--ticket", "t-2fa"],
    ["generate", "--customer", "marta", "--ticket", "t-2fa", "--text", "x"],  # ticket digitado não existe mais
    ["generate", "--customer", "marta", "--ticket", "t-2fa", "--type", "poema"],
])
def test_generate_argumentos_invalidos_sao_erro_de_uso(argv) -> None:
    with pytest.raises(SystemExit) as exc:
        main(argv)
    assert exc.value.code == EXIT_USAGE


@pytest.mark.parametrize("erro", [LLMUnavailable("fora do ar"), LLMRateLimited("muitas")])
def test_generate_erro_do_provedor_retorna_codigo_3_e_grava_a_execucao(settings, capsys, erro) -> None:
    container = build_container(settings, llm=LLMRoteirizado(erro))
    assert cli(["generate", "--customer", "marta", "--ticket", "t-2fa"], container) == EXIT_LLM
    assert str(erro) in capsys.readouterr().err
    assert json.loads(_salvos(settings)[0].read_text(encoding="utf-8"))["status"] == "error"


def test_generate_saida_invalida_apos_reparo_retorna_codigo_3(settings, capsys) -> None:
    container = build_container(settings, llm=LLMRoteirizado("{}", "{}"))
    assert cli(["generate", "--customer", "marta", "--ticket", "t-2fa"], container) == EXIT_LLM
    assert "reparo" in capsys.readouterr().err


def test_generate_como_modulo_sem_servidor(tmp_path: Path) -> None:
    """Caminho real de uso: a CLI em subprocesso executa direto sobre o núcleo e grava na pasta configurada."""
    env, data_dir = _cli_env(tmp_path)
    r = _modulo(env, "generate", "--customer", "jorge", "--ticket", "t-webhook")
    assert r.returncode == EXIT_OK, r.stderr
    assert "JSON salvo em:" in r.stdout
    [arquivo] = list((data_dir / "runs").rglob("*.json"))
    assert json.loads(arquivo.read_text(encoding="utf-8"))["provider"] == "fake"


# --- generate --type all ----------------------------------------------------------------------------


def test_generate_all_imprime_os_quatro_tipos_e_um_json_por_tipo(container, settings, capsys) -> None:
    assert cli(["generate", "--customer", "marta", "--ticket", "t-2fa", "--type", "all"], container) == EXIT_OK
    saida = capsys.readouterr().out
    for titulo in ("DIAGNÓSTICO", "PASSO A PASSO", "PERGUNTAS DE ESCLARECIMENTO", "RESUMO VISUAL DO FLUXO"):
        assert titulo in saida
    for trecho in ("HIPÓTESES", "PASSOS", "DÁ PARA AVANÇAR", "├─ Sim ─▶"):
        assert trecho in saida
    salvos = _salvos(settings)
    assert len(salvos) == 4 and all(str(a) in saida for a in salvos)


def test_generate_all_json(container, capsys) -> None:
    argv = ["generate", "--customer", "rafael", "--ticket", "t-webhook", "--type", "all", "--json"]
    assert cli(argv, container) == EXIT_OK
    itens = json.loads(capsys.readouterr().out)["results"]
    assert [i["content_type"] for i in itens] == [
        "diagnosis", "resolution_steps", "clarifying_questions", "flow_summary",
    ]
    assert all(i["error"] is None and i["saved_path"].endswith(".json") for i in itens)


def test_generate_all_com_falha_parcial_mostra_o_que_deu_certo_e_avisa(settings, capsys) -> None:
    """Como no site: só falha se todos falharem; se parte falhar, mostra o resto e avisa os tipos com erro."""
    from app.domain.models import FlowSummary, ResolutionSteps

    llm = LLMPorSchema({ResolutionSteps: LLMUnavailable("fora do ar"), FlowSummary: LLMUnavailable("fora do ar")})
    codigo = cli(["generate", "--customer", "marta", "--ticket", "t-2fa", "--type", "all"],
                 build_container(settings, llm=llm))
    saida, erro = capsys.readouterr()
    assert codigo == EXIT_OK
    assert erro.strip() == "aviso: Houve erro em: Passo a passo, Resumo visual do fluxo."
    assert "HIPÓTESES" in saida and "DÁ PARA AVANÇAR" in saida  # os tipos que deram certo saíram
    assert "PASSO A PASSO" not in saida and "FALHOU" not in saida
    assert len(_salvos(settings)) == 4  # as execuções com erro continuam no histórico


def test_generate_all_com_todos_falhando_sai_com_o_erro_do_primeiro(settings, capsys) -> None:
    from app.domain.models import ClarifyingQuestions, Diagnosis, FlowSummary, ResolutionSteps

    fora = LLMUnavailable("fora do ar")
    llm = LLMPorSchema({schema: fora for schema in (Diagnosis, ResolutionSteps, ClarifyingQuestions, FlowSummary)})
    codigo = cli(["generate", "--customer", "marta", "--ticket", "t-2fa", "--type", "all"],
                 build_container(settings, llm=llm))
    assert codigo == EXIT_LLM and "fora do ar" in capsys.readouterr().err


def test_generate_all_com_entrada_invalida_nao_gera(container, settings, capsys) -> None:
    assert cli(["generate", "--customer", "x", "--ticket", "t-2fa", "--type", "all"], container) == EXIT_NOT_FOUND
    assert _salvos(settings) == []


# --- cache (ADR 0028) --------------------------------------------------------------------------------


ARGS_CACHE = ["generate", "--customer", "marta", "--ticket", "t-2fa"]


def test_segunda_geracao_igual_mostra_cache_hit_e_nao_chama_o_llm(settings, capsys) -> None:
    llm = LLMPorSchema({})
    container = build_container(settings, llm=llm)
    assert cli(ARGS_CACHE, container) == EXIT_OK
    primeira = capsys.readouterr().out
    assert "cache hit" not in primeira
    assert cli(ARGS_CACHE, container) == EXIT_OK
    segunda = capsys.readouterr().out
    assert "cache hit (origem" in segunda and "HIPÓTESES" in segunda  # o conteúdo sai igual
    assert len(llm.chamadas) == 1 and len(_salvos(settings)) == 2


def test_no_cache_gera_de_novo(settings, capsys) -> None:
    llm = LLMPorSchema({})
    container = build_container(settings, llm=llm)
    cli(ARGS_CACHE, container)
    assert cli([*ARGS_CACHE, "--no-cache", "--confirm-replace"], container) == EXIT_OK
    assert "cache hit" not in capsys.readouterr().out.split("JSON salvo em")[1]
    assert len(llm.chamadas) == 2


def test_generate_json_traz_cache_hit_e_origem(settings, capsys) -> None:
    container = build_container(settings)
    cli([*ARGS_CACHE, "--json"], container)
    primeira = json.loads(capsys.readouterr().out)["run"]
    cli([*ARGS_CACHE, "--json"], container)
    segunda = json.loads(capsys.readouterr().out)["run"]
    assert primeira["cache_hit"] is False and segunda["cache_hit"] is True
    assert segunda["source_run_id"] == primeira["run_id"]


def test_generate_all_no_cache(settings, capsys) -> None:
    llm = LLMPorSchema({})
    container = build_container(settings, llm=llm)
    cli([*ARGS_CACHE, "--type", "all"], container)
    cli([*ARGS_CACHE, "--type", "all"], container)
    assert len(llm.chamadas) == 4  # a segunda rodada veio inteira do cache
    cli([*ARGS_CACHE, "--type", "all", "--no-cache", "--confirm-replace"], container)
    assert len(llm.chamadas) == 8


def test_no_cache_sobre_entrada_existente_lista_e_nao_gera_sem_confirm_replace(settings, capsys) -> None:
    llm = LLMPorSchema({})
    container = build_container(settings, llm=llm)
    cli(ARGS_CACHE, container)
    capsys.readouterr()
    assert cli([*ARGS_CACHE, "--no-cache"], container) == EXIT_USAGE
    erro = capsys.readouterr().err
    assert "substituiria 1 entrada(s) do cache" in erro and "--confirm-replace" in erro
    assert len(llm.chamadas) == 1  # nada foi gerado
    assert cli([*ARGS_CACHE, "--no-cache", "--confirm-replace"], container) == EXIT_OK
    assert len(llm.chamadas) == 2


# --- meta e CRUD do catálogo (o mesmo das abas Cliente e Ticket) ---------------------------------------------


def test_meta_mostra_o_mesmo_conteudo_de_api_meta(container, capsys) -> None:
    from fastapi.testclient import TestClient

    from app.adapters.api.main import create_app

    assert cli(["meta", "--json"], container) == EXIT_OK
    pela_cli = json.loads(capsys.readouterr().out)
    assert pela_cli == TestClient(create_app(container, frontend_dist=None)).get("/api/meta").json()
    assert cli(["meta"], container) == EXIT_OK
    saida = capsys.readouterr().out
    assert f"Versão padrão:     {LATEST_VERSION}" in saida and "itens por página: 10, 20, 50, 100" in saida


def test_crud_de_cliente(container, capsys) -> None:
    criar = ["profile", "create", "--name", "Teste", "--tech-level", "leigo", "--comm-style", "direto",
             "--channel", "chat", "--json"]
    assert cli(criar, container) == EXIT_OK
    novo = json.loads(capsys.readouterr().out)
    assert novo["id"].startswith("c-") and container.profiles.get(novo["id"]).name == "Teste"
    assert cli(["profile", "update", novo["id"], "--channel", "e-mail"], container) == EXIT_OK
    assert "Cliente atualizado" in capsys.readouterr().out
    atualizado = container.profiles.get(novo["id"])
    assert atualizado.channel.value == "e-mail" and atualizado.name == "Teste"  # o que não veio ficou como estava
    assert cli(["profile", "delete", novo["id"], "--yes"], container) == EXIT_OK
    assert cli(["profile", "list", "--id", novo["id"]], container) == EXIT_NOT_FOUND


def test_remover_sem_confirmar_nao_remove(container, capsys, monkeypatch) -> None:
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    assert cli(["profile", "delete", "marta"], container) == EXIT_OK
    assert "Remoção cancelada" in capsys.readouterr().out and container.profiles.get("marta")

    def sem_stdin(prompt: str = "") -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", sem_stdin)
    assert cli(["ticket", "delete", "t-2fa"], container) == EXIT_USAGE
    assert "--yes" in capsys.readouterr().err and container.tickets.get("t-2fa")


def test_crud_de_ticket_e_validacao_do_servidor(container, capsys) -> None:
    assert cli(["ticket", "create", "--title", "Erro X", "--text", "O relato.", "--json"], container) == EXIT_OK
    novo = json.loads(capsys.readouterr().out)["id"]
    assert cli(["ticket", "update", novo, "--title", "Erro Y"], container) == EXIT_OK
    assert container.tickets.get(novo).title == "Erro Y" and container.tickets.get(novo).text == "O relato."
    assert cli(["ticket", "create", "--title", "  ", "--text", "x"], container) == EXIT_USAGE
    assert "Informe o título do ticket" in capsys.readouterr().err
    assert cli(["ticket", "delete", novo, "--yes"], container) == EXIT_OK
    assert cli(["ticket", "update", novo, "--title", "z"], container) == EXIT_NOT_FOUND


# --- histórico paginado (o mesmo do site) -------------------------------------------------------------------


def test_history_pagina_com_os_tamanhos_do_site_e_filtra_pela_chave(settings, capsys) -> None:
    from tests.support import gerar_versoes, seed_prompt_versions

    seed_prompt_versions(settings.prompts_dir, "v2", "v3")
    container = build_container(settings)
    for _ in range(3):
        gerar_versoes(container, ("v1", "v2", "v3"), nova=True)  # 9 execuções, 3 por versão
    assert cli(["history", "generation", "--limit", "10", "--json"], container) == EXIT_OK
    pagina = json.loads(capsys.readouterr().out)
    assert pagina["total"] == 9 and len(pagina["items"]) == 9
    assert cli(["history", "generation", "--limit", "7"], container) == EXIT_USAGE
    assert "10, 20, 50, 100" in capsys.readouterr().err
    assert cli(["history", "generation", "--limit", "10", "--page", "2"], container) == EXIT_USAGE
    assert "A página 2 não existe: há 1." in capsys.readouterr().err
    assert cli(["history", "generation", "--limit", "20"], container) == EXIT_OK
    assert "Página 1 de 1 · 9 execuções (20 por página)" in capsys.readouterr().out
    chave = pagina["items"][0]["cache_key"]
    assert cli(["history", "generation", "--cache-key", chave[:12], "--json"], container) == EXIT_OK
    equivalentes = json.loads(capsys.readouterr().out)
    assert equivalentes["total"] == 3 and {r["cache_key"] for r in equivalentes["items"]} == {chave}
