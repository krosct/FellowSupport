"""Configuração única da aplicação (ADR 0011).

Todas as variáveis do ``.env`` são lidas aqui e em nenhum outro lugar: o resto do código recebe um
``Settings`` já validado. Isso mantém tipos, padrões e segredos num único ponto (SSOT).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.ports.llm import ReasoningMode, StructuredMode

# Raiz do repositório. Caminhos relativos do .env (ex.: ``catalog``) são resolvidos a partir dela, para que a
# API e a CLI funcionem independentemente do diretório em que são iniciadas.
BASE_DIR = Path(__file__).resolve().parent.parent

# Build do front-end servido em "/" quando existir (ADR 0012).
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"

# Provedores aceitos. ``fake`` roda o projeto inteiro sem chave (ADR 0023).
LlmProvider = Literal["openrouter", "fake"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]


class Settings(BaseSettings):
    """Configuração tipada, preenchida por variáveis de ambiente e pelo arquivo ``.env``.

    Os nomes dos campos correspondem, em minúsculas, às variáveis de ``.env.example``.
    """

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",  # variáveis desconhecidas no ambiente não quebram a inicialização
        case_sensitive=False,
    )

    # --- Provedor de LLM ---
    llm_provider: LlmProvider = "fake"
    # SecretStr: o repr e o model_dump mostram "**********", nunca o valor real.
    openrouter_api_key: SecretStr = SecretStr("")
    llm_base_url: str = "https://openrouter.ai/api/v1"
    # Padrão gratuito com JSON estruturado; alternativa documentada: nvidia/nemotron-3.5-super-vl:free
    llm_model: str = "baidu/ernie-5.5-flash-preview:free"
    llm_judge_model: str = ""  # vazio = mesmo modelo de geração
    llm_temperature: float = 0.2
    # Folga para modelos de raciocínio, que gastam milhares de tokens "pensando" antes do JSON (ADR 0026).
    llm_max_tokens: int = 8000
    llm_timeout_s: float = 60
    llm_max_retries: int = 2
    llm_structured_mode: StructuredMode = "json_schema"
    # Controle do raciocínio dos modelos que "pensam" antes de responder (ADR 0027); "default" não envia nada.
    llm_reasoning: ReasoningMode = "default"

    # --- Prompts e dados ---
    default_prompt_version: str = "v1"
    prompts_dir: Path = Path("prompts")
    catalog_dir: Path = Path("catalog")
    data_dir: Path = Path("var")
    cache_enabled: bool = True
    save_prompt_messages: bool = True
    max_ticket_chars: int = 4000
    app_timezone: str = "America/Sao_Paulo"

    # --- Servidor web ---
    host: str = "127.0.0.1"
    port: int = 8000
    rate_limit_per_min: int = 10
    log_level: LogLevel = "INFO"
    public_url: str = ""

    @field_validator("prompts_dir", "catalog_dir", "data_dir")
    @classmethod
    def _resolve_relative_to_base(cls, value: Path) -> Path:
        """Resolve pastas relativas a partir da raiz do repositório (e não do diretório atual)."""
        return value if value.is_absolute() else BASE_DIR / value

    @property
    def judge_model(self) -> str:
        """Modelo do LLM-juiz: ``LLM_JUDGE_MODEL`` ou, se vazio, o modelo de geração."""
        return self.llm_judge_model or self.llm_model


@lru_cache
def get_settings() -> Settings:
    """Devolve o ``Settings`` do processo (carregado uma vez; testes constroem o seu próprio)."""
    return Settings()
