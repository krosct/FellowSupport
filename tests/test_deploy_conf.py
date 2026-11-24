"""Contrato do ``deploy.conf`` com o resto do projeto (Etapa 7).

O script de deploy lê o arquivo como ``CHAVE=valor`` (sem executá-lo). Estes testes leem do mesmo jeito e conferem que o
que o arquivo promete existe de verdade: variáveis que o ``Settings`` lê, rota de saúde servida, pastas de execução no
pacote e porta de desenvolvimento igual ao padrão do app. Sem rede e sem tocar em ``var/`` (ADR 0016).
"""

import re

import pytest
from fastapi.testclient import TestClient

from app.adapters.api.main import create_app
from app.config import BASE_DIR, Settings
from app.container import build_container

CONF = BASE_DIR / "deploy.conf"

# Itens do pacote que o servidor lê em tempo de execução: nenhum pode cair no EXCLUDE.
RUNTIME_PATHS = ["app", "catalog", "prompts", "requirements.txt", "deploy.conf", "frontend/dist"]


def _conf() -> dict[str, str]:
    """Lê o arquivo como o script: a última ``CHAVE=valor`` de cada chave, sem aspas externas, comentários ignorados."""
    values: dict[str, str] = {}
    for line in CONF.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\s*([A-Z_]+)\s*=\s*(.*?)\s*$", line)
        if match:
            value = match.group(2)
            values[match.group(1)] = re.sub(r'^"(.*)"$', r"\1", value)
    return values


@pytest.fixture(scope="module")
def conf() -> dict[str, str]:
    return _conf()


def test_chaves_obrigatorias_do_script_e_a_proibida(conf: dict[str, str]) -> None:
    assert conf["APP"] == "fellowsupport" and re.fullmatch(r"[a-z][a-z0-9-]{1,30}", conf["APP"])
    for chave in ("DEV", "INSTALL", "RUN", "BUILD", "INCLUDE", "EXCLUDE", "HEALTH", "REQUIRED", "MEMORY_MAX",
                  "SERVICE_ENV"):
        assert conf.get(chave), chave
    # O site precisa de todos os caminhos: PUBLIC_PATHS fecharia o resto com 404.
    assert "PUBLIC_PATHS" not in conf and "PRESERVE" not in conf


def test_instalacao_de_producao_usa_python_3_12_e_sem_dependencias_de_dev(conf: dict[str, str]) -> None:
    for chave in ("INSTALL", "DEV"):
        assert "uv venv .venv --python 3.12" in conf[chave]
        assert "uv pip install --python .venv/bin/python -r requirements.txt" in conf[chave]
        assert "requirements-dev" not in conf[chave]


def test_run_segue_o_contrato_do_proxy_e_de_um_unico_worker(conf: dict[str, str]) -> None:
    run = conf["RUN"]
    assert "app.adapters.api.main:app" in run
    assert "--host 127.0.0.1" in run and "--port {port}" in run
    assert "--workers 1" in run, "o limite de taxa é em memória (ADR 0033)"
    assert "--proxy-headers" in run and "--forwarded-allow-ips 127.0.0.1" in run and "--no-server-header" in run


def test_porta_do_dev_e_o_padrao_do_settings(conf: dict[str, str]) -> None:
    """A porta padrão do ``DEV`` (``${PORT:-N}``) é a do ``Settings``: um único valor para o projeto inteiro."""
    achado = re.search(r"\$\{PORT:-(\d+)\}", conf["DEV"])
    assert achado and int(achado.group(1)) == Settings.model_fields["port"].default


def test_service_env_aponta_para_a_pasta_persistente_e_usa_campos_do_settings(conf: dict[str, str]) -> None:
    itens = dict(item.split("=", 1) for item in conf["SERVICE_ENV"].split())
    assert itens["DATA_DIR"] == "{data}" and itens["PUBLIC_URL"] == "{url}" and itens["PYTHONUNBUFFERED"] == "1"
    campos = {nome.upper() for nome in Settings.model_fields}
    assert {"DATA_DIR", "PUBLIC_URL"} <= campos
    assert conf["REQUIRED"] == "ADMIN_API_KEY" and "ADMIN_API_KEY" in campos


def test_memory_max_tem_o_formato_aceito_pelo_script(conf: dict[str, str]) -> None:
    assert re.fullmatch(r"[0-9]+[KMGT]?", conf["MEMORY_MAX"])


def test_exclude_nao_cobre_o_include_nem_o_que_o_servidor_le(conf: dict[str, str]) -> None:
    """Mesmas regras do script: o EXCLUDE não pode cobrir (nem estar dentro de) um INCLUDE, nem tirar o deploy.conf."""
    # Garante que nenhuma regra de EXCLUDE apague arquivos usados em produção ou do build.
    excluidos = [e.removeprefix("./").rstrip("/") for e in conf["EXCLUDE"].split()]
    incluidos = [i.removeprefix("./").rstrip("/") for i in conf["INCLUDE"].split()]
    assert incluidos == ["frontend/dist"]
    for exc in excluidos:
        assert exc and not exc.startswith("/") and ".." not in exc
        for caminho in [*incluidos, *RUNTIME_PATHS]:
            assert not f"{caminho}/".startswith(f"{exc}/"), f"EXCLUDE {exc} cobre {caminho}"
        for inc in incluidos:
            assert not f"{exc}/".startswith(f"{inc}/"), f"EXCLUDE {exc} está dentro de {inc}"


def test_pastas_do_settings_existem_na_raiz_do_pacote() -> None:
    """``CATALOG_DIR`` e ``PROMPTS_DIR`` (relativos à raiz do app) apontam para pastas versionadas e não excluídas."""
    padrao = Settings()
    for pasta in (padrao.catalog_dir, padrao.prompts_dir):
        assert pasta.is_dir() and pasta.parent == BASE_DIR


def test_rota_de_saude_do_deploy_responde_200(conf: dict[str, str], settings: Settings) -> None:
    cliente = TestClient(create_app(build_container(settings), frontend_dist=None))
    assert cliente.get(conf["HEALTH"]).status_code == 200
