"""Fixtures compartilhadas: isolam os testes do ambiente e do ``.env`` real do autor."""

from __future__ import annotations

import pytest

from app.config import BASE_DIR, Settings

# Variáveis lidas por Settings; removidas do ambiente para os testes serem herméticos.
_SETTINGS_ENV_VARS = [name.upper() for name in Settings.model_fields]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove do ambiente qualquer variável de configuração antes de cada teste."""
    for name in _SETTINGS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def settings() -> Settings:
    """Settings só com os padrões (sem ler o ``.env``) e o catálogo real do repositório."""
    return Settings(_env_file=None, catalog_dir=BASE_DIR / "catalog")
