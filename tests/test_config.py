"""Testes do Settings: padrões seguros, segredo protegido e resolução de pastas."""

from pathlib import Path

from pydantic import SecretStr

from app.config import BASE_DIR, Settings

SEGREDO = "sk-or-v1-segredo-de-teste-1234567890"


def test_defaults_usam_provedor_fake_sem_chave() -> None:
    s = Settings()
    assert s.llm_provider == "fake"
    assert s.openrouter_api_key.get_secret_value() == ""
    assert s.llm_structured_mode == "json_schema"


def test_repr_e_dump_nao_vazam_a_chave() -> None:
    s = Settings(openrouter_api_key=SecretStr(SEGREDO), admin_api_key=SecretStr("admin-" + SEGREDO))
    assert SEGREDO not in repr(s)
    assert SEGREDO not in str(s)
    assert SEGREDO not in str(s.model_dump())
    assert SEGREDO not in s.model_dump_json()
    # O valor continua acessível de forma explícita para o adaptador de LLM e autenticação admin.
    assert s.openrouter_api_key.get_secret_value() == SEGREDO
    assert s.admin_api_key.get_secret_value() == "admin-" + SEGREDO


def test_llm_base_url_exige_https_remoto_e_aceita_http_local() -> None:
    import pytest

    assert Settings(llm_base_url="https://openrouter.ai/api/v1").llm_base_url == "https://openrouter.ai/api/v1"
    assert Settings(llm_base_url="http://127.0.0.1:11434/v1").llm_base_url == "http://127.0.0.1:11434/v1"
    assert Settings(llm_base_url="http://localhost:8000/v1").llm_base_url == "http://localhost:8000/v1"
    with pytest.raises(ValueError, match="https://"):
        Settings(llm_base_url="http://api.exemplo.com/v1")


def test_le_variaveis_do_ambiente(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", SEGREDO)
    monkeypatch.setenv("LLM_MAX_TOKENS", "900")
    s = Settings()
    assert s.llm_provider == "openrouter"
    assert s.llm_max_tokens == 900
    assert SEGREDO not in repr(s)


def test_pastas_relativas_partem_da_raiz_do_repositorio() -> None:
    s = Settings()
    assert s.catalog_dir == BASE_DIR / "catalog"
    assert s.data_dir == BASE_DIR / "var"
    assert Settings(data_dir=Path("/tmp/x")).data_dir == Path("/tmp/x")


def test_env_example_e_settings_tem_as_mesmas_variaveis() -> None:
    """Toda variável do .env.example existe no Settings (e vice-versa): evita configuração órfã."""
    # Confere que todas as chaves de .env.example correspondem aos campos de Settings.
    linhas = (BASE_DIR / ".env.example").read_text(encoding="utf-8").splitlines()
    no_exemplo = {ln.split("=", 1)[0] for ln in linhas if ln and not ln.startswith("#") and "=" in ln}
    no_settings = {name.upper() for name in Settings.model_fields}
    assert no_exemplo == no_settings
