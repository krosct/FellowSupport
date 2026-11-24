"""Fixtures compartilhadas: isolam os testes do ambiente e do ``.env`` real do autor."""

import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from app.config import BASE_DIR, Settings
from app.domain.models import RunRecord

# Variáveis lidas por Settings; removidas do ambiente para os testes serem herméticos.
_SETTINGS_ENV_VARS = [name.upper() for name in Settings.model_fields]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Remove do ambiente qualquer variável de configuração e desliga a leitura do ``.env`` antes de cada teste.

    O log de eventos vai para a pasta temporária do teste: nenhum teste escreve no ``fellowsupport.log`` real.
    """
    # Remove todas as variáveis do Settings do ambiente antes de cada teste.
    for name in _SETTINGS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    monkeypatch.setenv("LOG_FILE", str(tmp_path / "fellowsupport.log"))


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Settings só com os padrões (sem ler o ``.env``, provedor ``fake``), uma **cópia** dos prompts e do
    catálogo e os dados em pastas temporárias: os testes nunca escrevem em ``prompts/``, ``catalog/`` nem ``var/``
    reais (ADR 0016 e 0037)."""
    # Monta um Settings isolado em tmp_path usando provedor fake e cópias de catalog/ e prompts/.
    catalog_dir = tmp_path / "catalog"
    prompts_dir = tmp_path / "prompts"
    shutil.copytree(BASE_DIR / "catalog", catalog_dir)
    shutil.copytree(BASE_DIR / "prompts", prompts_dir)
    return Settings(
        llm_provider="fake",
        catalog_dir=catalog_dir,
        prompts_dir=prompts_dir,
        data_dir=tmp_path / "var",
    )


@pytest.fixture
def make_record() -> Callable[..., RunRecord]:
    """Fábrica de ``RunRecord`` válidos; ``make_record(campo=valor)`` sobrescreve campos."""

    # Cria um RunRecord válido padrão permitindo sobrescrever qualquer campo via kwargs.
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
