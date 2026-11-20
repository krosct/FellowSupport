"""Restrições de formato por canal de atendimento (item 4.2 do PDF: "restrições da saída").

Uma só tabela (SSOT) alimenta duas coisas: o texto de instrução inserido nos prompts (``$channel_format``) e a
verificação por código da saída. Assim, o que o prompt pede e o que o sistema confere não divergem. São regras
de **formato** (como o texto é entregue), não de vocabulário ou profundidade: a adaptação ao nível técnico fica
para as versões de prompt.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from app.domain.models import Channel

# Instrução, em pt-BR, inserida no prompt de cada tipo conforme o canal do perfil.
CHANNEL_FORMAT_RULES: dict[Channel, str] = {
    Channel.TELEFONE: (
        "o texto será lido em voz alta por telefone: use frases curtas e faladas, sem markdown, sem listas, "
        "sem símbolos e sem siglas soletradas."
    ),
    Channel.CHAT: "mensagens curtas e diretas, em tom de conversa; evite blocos longos de texto.",
    Channel.EMAIL: "texto completo e cordial, com frases inteiras; pode usar saudação e fechamento.",
}

# Canais cujo texto não pode conter markdown (quem lê não vê formatação: ouve).
_NO_MARKDOWN_CHANNELS = frozenset({Channel.TELEFONE})

# Marcas de markdown: negrito/itálico forte, crase, título, item de lista (com marcador ou número) e link.
_MARKDOWN = re.compile(
    r"\*\*|__|`|^\s{0,3}#{1,6}\s|^\s*[-*•]\s|^\s*\d+[.)]\s|\[[^\]]+\]\([^)]+\)",
    re.MULTILINE,
)


def channel_format_instruction(channel: Channel) -> str:
    """Instrução de formato do canal, para inserir no prompt."""
    return CHANNEL_FORMAT_RULES[channel]


def _strings(value: object) -> list[str]:
    """Todos os textos de um JSON aninhado (valores, não chaves)."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _strings(item)]
    if isinstance(value, list):
        return [text for item in value for text in _strings(item)]
    return []


def find_channel_violations(channel: Channel, output: BaseModel) -> str:
    """Descreve, em uma frase, a violação das restrições do canal na saída; ``""`` se não houver.

    O texto volta ao modelo no reparo (ADR 0004), então diz o que corrigir. Hoje só o telefone é verificável por
    código (sem markdown); as demais regras são orientação do prompt.
    """
    if channel not in _NO_MARKDOWN_CHANNELS:
        return ""
    for text in _strings(output.model_dump(mode="json")):
        found = _MARKDOWN.search(text)
        if found:
            return (
                f"O canal {channel.value} não aceita markdown, mas o texto {text[:60]!r} contém "
                f"{found.group(0).strip()!r}. Reescreva em frases corridas, sem marcadores, números de lista, "
                "negrito, títulos ou crases."
            )
    return ""
