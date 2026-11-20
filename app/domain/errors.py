"""Exceções do domínio (ADR 0018).

O núcleo lança apenas estas exceções. Os adaptadores de entrada as traduzem: a API para códigos HTTP e a
CLI para códigos de saída. Erros de bibliotecas externas são convertidos nelas dentro dos adaptadores.
"""

from __future__ import annotations


class DomainError(Exception):
    """Base de todas as falhas esperadas da aplicação."""


class NotFound(DomainError):
    """Entidade inexistente (perfil, ticket, execução). HTTP 404."""


class ValidationFailed(DomainError):
    """Entrada ou dado inválido (ex.: catálogo malformado, ticket grande demais). HTTP 422."""


class LLMUnavailable(DomainError):
    """Provedor de LLM fora do ar, sem chave ou com erro de rede. HTTP 503."""


class LLMRateLimited(DomainError):
    """Provedor de LLM recusou por excesso de requisições (429). HTTP 429."""


class InvalidLLMOutput(DomainError):
    """O modelo respondeu algo que não valida contra o schema, mesmo após o reparo. HTTP 502."""
