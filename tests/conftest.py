"""Fixtures compartilhadas: isolam os testes do ambiente e do ``.env`` real do autor."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from app.config import BASE_DIR, Settings
from app.domain.models import RunRecord

# Variáveis lidas por Settings; removidas do ambiente para os testes serem herméticos.
_SETTINGS_ENV_VARS = [name.upper() for name in Settings.model_fields]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove do ambiente qualquer variável de configuração antes de cada teste."""
    for name in _SETTINGS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Settings só com os padrões (sem ler o ``.env``, provedor ``fake``), o catálogo e os prompts reais do
    repositório e os dados em pasta temporária: os testes nunca escrevem no ``var/`` real (ADR 0016)."""
    return Settings(
        _env_file=None,
        llm_provider="fake",
        catalog_dir=BASE_DIR / "catalog",
        prompts_dir=BASE_DIR / "prompts",
        data_dir=tmp_path / "var",
    )


@pytest.fixture
def make_record() -> Callable[..., RunRecord]:
    """Fábrica de ``RunRecord`` válidos; ``make_record(campo=valor)`` sobrescreve campos."""

    def _make(**changes: object) -> RunRecord:
        base: dict = {
            "run_id": "abc123def456",
            "timestamp": "2026-11-20T14:03:11-03:00",
            "status": "ok",
            "customer_id": "marta",
            "customer_profile": {
                "id": "marta", "name": "Dona Marta", "tech_level": "leigo",
                "comm_style": "didático", "channel": "telefone",
            },
            "ticket": {"id": "t-2fa", "title": "SMS não chega", "text": "Texto do ticket"},
            "content_type": "diagnosis",
            "prompt_version": "v1",
            "prompt_sha256": "0" * 64,
            "provider": "fake",
            "model": "vendor/modelo:free",
            "params": {"temperature": 0.2, "max_tokens": 1500, "structured_mode": "json_schema"},
        }
        return RunRecord.model_validate({**base, **changes})

    return _make
