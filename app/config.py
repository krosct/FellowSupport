"""Configuração única da aplicação (ADR 0011).

Todas as variáveis do ``.env`` são lidas aqui e em nenhum outro lugar: o resto do código recebe um
``Settings`` já validado. Isso mantém tipos, padrões e segredos num único ponto (SSOT - Single Source of Truth).
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
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

    # Lê variáveis do .env na raiz do projeto e ignora campos desconhecidos.
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
    # Chave administrativa para gerenciar clientes, tickets e prompts na API HTTP (em deploy, inserida na sessão).
    admin_api_key: SecretStr = SecretStr("")
    llm_base_url: str = "https://openrouter.ai/api/v1"
    # Padrão gratuito com JSON estruturado; alternativa documentada: nvidia/nemotron-3.5-super-vl:free
    llm_model: str = "baidu/ernie-5.5-flash-preview:free"
    llm_temperature: float = 0.1
    # Folga para modelos de raciocínio, que gastam milhares de tokens "pensando" antes do JSON (ADR 0026).
    llm_max_tokens: int = 12000
    llm_timeout_s: float = 90
    llm_max_retries: int = 2
    llm_structured_mode: StructuredMode = "json_schema"
    # Controle do raciocínio dos modelos que "pensam" antes de responder (ADR 0027); "default" não envia nada.
    llm_reasoning: ReasoningMode = "default"

    # --- Prompts e dados ---
    prompts_dir: Path = Path("prompts")
    catalog_dir: Path = Path("catalog")
    data_dir: Path = Path("var")
    save_prompt_messages: bool = True
    max_ticket_chars: int = 4000
    app_timezone: str = "America/Sao_Paulo"

    # --- Servidor web ---
    host: str = "127.0.0.1"
    port: int = 9713
    # Chamadas por minuto, por IP, nas rotas que chamam o LLM; 0 desliga o limite (ADR 0033).
    rate_limit_per_min: int = Field(default=10, ge=0)
    log_level: LogLevel = "INFO"
    # Log de eventos em JSON Lines (ADR 0043): cada geração, lote, avaliação e comparação vira uma linha.
    log_file: Path = Path("fellowsupport.log")
    public_url: str = ""

    @field_validator("prompts_dir", "catalog_dir", "data_dir", "log_file")
    @classmethod
    def _resolve_relative_to_base(cls, value: Path) -> Path:
        """Resolve caminhos relativos a partir da raiz do repositório (e não do diretório atual)."""
        # Mantém caminhos absolutos e resolve os relativos pela raiz BASE_DIR.
        return value if value.is_absolute() else BASE_DIR / value

    @field_validator("llm_base_url")
    @classmethod
    def _require_https_for_remote_llm(cls, value: str) -> str:
        """Exige HTTPS para endpoints remotos, evitando tráfego da chave em texto claro."""
        cleaned = value.strip()
        parsed = urlsplit(cleaned)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError("LLM_BASE_URL deve ser uma URL válida (ex.: https://openrouter.ai/api/v1).")
        scheme = parsed.scheme.lower()
        host = (parsed.hostname or "").lower()
        if scheme == "https":
            return cleaned
        if scheme == "http" and host in {"localhost", "127.0.0.1", "::1"}:
            return cleaned
        raise ValueError("LLM_BASE_URL deve usar https:// (http:// só é permitido para localhost/127.0.0.1).")


@lru_cache
def get_settings() -> Settings:
    """Devolve o ``Settings`` do processo (carregado uma vez; testes constroem o seu próprio)."""
    return Settings()
