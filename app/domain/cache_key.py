"""Chave de cache canônica (ADR 0010 e 0028): função pura que decide quando duas gerações são equivalentes.

A chave é o SHA-256 do JSON canônico (chaves ordenadas, sem espaços) de tudo o que influencia a saída do modelo:
o **conteúdo** do perfil (e não só o id: editar o perfil invalida o cache), o ticket normalizado, o tipo de
conteúdo, a versão e o hash do prompt, o provedor, o modelo e os parâmetros de geração. Qualquer mudança em um
desses campos muda a chave; diferença só de espaços no ticket ou de ordem das chaves não muda.

Fica no domínio porque é regra de negócio (o que é "equivalente"), sem I/O: recebe valores simples e devolve texto.
"""

import hashlib
import json

from app.domain.models import ContentType, CustomerProfile


def normalize_ticket(text: str) -> str:
    """Normaliza o texto do ticket: remove espaços nas pontas e colapsa qualquer sequência de espaços em um.

    ``str.split()`` sem argumento já trata espaços, tabs e quebras de linha como separadores. A quebra de linha
    deixa de ser distinguível de um espaço, o que é aceitável: o relato do cliente é prosa, não formato.
    """
    return " ".join(text.split())


def compute_cache_key(
    *,
    profile: CustomerProfile,
    ticket_text: str,
    content_type: ContentType,
    prompt_version: str,
    prompt_sha256: str,
    provider: str,
    model: str,
    temperature: float,
    max_tokens: int,
    structured_mode: str,
    reasoning: str,
) -> str:
    """Devolve a chave de cache (64 caracteres hexadecimais) da geração descrita pelos argumentos.

    ``prompt_sha256`` é o hash dos arquivos do prompt no momento da execução (e não o ``meta.json``), então
    editar um prompt sem criar versão nova também invalida o cache, em vez de devolver saída desatualizada.
    """
    # Reúne tudo que influencia a resposta para gerar um hash SHA-256 único.
    payload = {
        "profile": profile.model_dump(mode="json"),
        "ticket": normalize_ticket(ticket_text),
        "content_type": content_type.value,
        "prompt_version": prompt_version,
        "prompt_sha256": prompt_sha256,
        "provider": provider,
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "structured_mode": structured_mode,
        "reasoning": reasoning,
    }
    # sort_keys + separadores sem espaço = forma canônica; ensure_ascii=False mantém a acentuação estável.
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
