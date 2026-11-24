"""Exceções do domínio (ADR 0018).

O núcleo lança apenas estas exceções. Os adaptadores de entrada as traduzem: a API para códigos HTTP e a
CLI para códigos de saída. Erros de bibliotecas externas são convertidos nelas dentro dos adaptadores.
"""

from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # só para tipos: o domínio de erros não importa os modelos em tempo de execução
    from app.domain.models import CacheConflict

# Mensagem única do 429: curta, em pt-BR e sem o texto cru do provedor (que vai só para o log). Fica aqui para o
# adaptador de LLM, a API e a CLI mostrarem exatamente a mesma frase (SSOT).
RATE_LIMIT_MESSAGE = "Limite do modelo gratuito atingido; tente em instantes."


class DomainError(Exception):
    """Base de todas as falhas esperadas da aplicação."""


class NotFound(DomainError):
    """Entidade inexistente (perfil, ticket, execução). HTTP 404."""


class ValidationFailed(DomainError):
    """Entrada ou dado inválido (ex.: catálogo malformado, ticket grande demais). HTTP 422."""


class CacheReplaceRequired(DomainError):
    """Gerar sem consultar o cache substituiria entradas já guardadas e o pedido não confirmou. HTTP 409.

    Leva **todas** as entradas afetadas pelo pedido (``conflicts``), para o cliente mostrá-las juntas e repetir o
    pedido com ``confirm_replace`` (API) ou ``--confirm-replace`` (CLI). Nada foi gerado quando ela é levantada.
    """

    def __init__(self, conflicts: "Sequence[CacheConflict]") -> None:
        self.conflicts = list(conflicts)
        lines = "\n".join(f"- {conflict.describe()}" for conflict in self.conflicts)
        super().__init__(f"O pedido substituiria {len(self.conflicts)} entrada(s) do cache:\n{lines}")


class LLMUnavailable(DomainError):
    """Provedor de LLM fora do ar, sem chave ou com erro de rede. HTTP 503."""


class LLMRateLimited(DomainError):
    """Provedor de LLM recusou por excesso de requisições (429). HTTP 429."""


class InvalidLLMOutput(DomainError):
    """O modelo respondeu algo que não valida contra o schema, mesmo após o reparo. HTTP 502."""


class Unauthorized(DomainError):
    """Credencial ausente ou inválida para operação protegida. HTTP 401."""


class Forbidden(DomainError):
    """Operação administrativa bloqueada por falta de configuração no servidor. HTTP 403."""
