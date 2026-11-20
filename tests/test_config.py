"""Testes do Settings: padrões seguros, segredo protegido e resolução de pastas."""

from __future__ import annotations

from pathlib import Path

from app.config import BASE_DIR, Settings

SEGREDO = "sk-or-v1-segredo-de-teste-1234567890"


def test_defaults_usam_provedor_fake_sem_chave() -> None:
    s = Settings(_env_file=None)
    assert s.llm_provider == "fake"
    assert s.openrouter_api_key.get_secret_value() == ""
    assert s.llm_structured_mode == "json_schema"
    assert s.default_prompt_version == "v1"


def test_repr_e_dump_nao_vazam_a_chave() -> None:
    s = Settings(_env_file=None, openrouter_api_key=SEGREDO)
    assert SEGREDO not in repr(s)
    assert SEGREDO not in str(s)
    assert SEGREDO not in str(s.model_dump())
    assert SEGREDO not in s.model_dump_json()
    # O valor continua acessível de forma explícita para o adaptador de LLM.
    assert s.openrouter_api_key.get_secret_value() == SEGREDO


def test_le_variaveis_do_ambiente(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", SEGREDO)
    monkeypatch.setenv("LLM_MAX_TOKENS", "900")
    monkeypatch.setenv("CACHE_ENABLED", "false")
    s = Settings(_env_file=None)
    assert s.llm_provider == "openrouter"
    assert s.llm_max_tokens == 900
    assert s.cache_enabled is False
    assert SEGREDO not in repr(s)


def test_pastas_relativas_partem_da_raiz_do_repositorio() -> None:
    s = Settings(_env_file=None)
    assert s.catalog_dir == BASE_DIR / "catalog"
    assert s.data_dir == BASE_DIR / "var"
    assert Settings(_env_file=None, data_dir=Path("/tmp/x")).data_dir == Path("/tmp/x")


def test_modelo_padrao_do_settings_e_do_env_example_coincidem() -> None:
    """O padrão do código e o do .env.example não podem divergir."""
    linhas = (BASE_DIR / ".env.example").read_text(encoding="utf-8").splitlines()
    modelo = next(ln.split("=", 1)[1] for ln in linhas if ln.startswith("LLM_MODEL="))
    assert Settings(_env_file=None).llm_model == modelo == "baidu/ernie-5.5-flash-preview:free"


def test_juiz_usa_o_modelo_de_geracao_quando_vazio() -> None:
    assert Settings(_env_file=None, llm_model="a/b").judge_model == "a/b"
    assert Settings(_env_file=None, llm_model="a/b", llm_judge_model="c/d").judge_model == "c/d"


def test_env_example_e_settings_tem_as_mesmas_variaveis() -> None:
    """Toda variável do .env.example existe no Settings (e vice-versa): evita configuração órfã."""
    linhas = (BASE_DIR / ".env.example").read_text(encoding="utf-8").splitlines()
    no_exemplo = {ln.split("=", 1)[0] for ln in linhas if ln and not ln.startswith("#") and "=" in ln}
    no_settings = {name.upper() for name in Settings.model_fields}
    assert no_exemplo == no_settings
