"""Funções puras para tratar a saída bruta de um LLM: extrair o JSON e resumir erros de validação.

Ficam no domínio porque são regras sobre o formato da resposta, usadas tanto pelos adaptadores (que preenchem
``LLMResult.parsed``) quanto pelo serviço (que monta a mensagem de reparo).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator

from pydantic import ValidationError

# Cerca de código Markdown que alguns modelos colocam em volta do JSON (```json ... ```).
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)

# Quantidade máxima de erros de validação devolvidos ao modelo no reparo (mantém o prompt curto).
MAX_REPAIR_ERRORS = 8


def _top_level_starts(text: str) -> Iterator[int]:
    """Posições das ``{`` que abrem um bloco de nível zero (fora de qualquer outro bloco ``{...}``).

    Percorre o texto contando a profundidade das chaves e ignorando as que aparecem dentro de strings JSON.
    Só olha o nível zero para não confundir um objeto **interno** de uma resposta truncada com a resposta inteira:
    se o objeto externo nunca fecha, a profundidade não volta a zero e nenhum candidato falso aparece.
    """
    depth, in_string, escaped = 0, False, False
    for index, char in enumerate(text):
        if depth and in_string:
            # Dentro de uma string JSON, só a aspa não escapada a fecha (``\"`` e ``\\`` tratados em ``escaped``).
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == "{":
            if depth == 0:
                yield index
            depth += 1
        elif char == "}" and depth:
            depth -= 1
        elif char == '"' and depth:
            in_string = True


def extract_json_object(text: str) -> dict | None:
    """Extrai o primeiro objeto JSON do texto, ou ``None`` se não houver um objeto decodificável.

    Tenta, em ordem: o texto inteiro, o conteúdo de uma cerca de código e cada bloco ``{...}`` de nível zero
    decodificado a partir da sua abertura. O último passo cobre o modelo que "conversa" em volta, inclusive com
    chaves soltas no texto antes ou depois do JSON (o corte ingênuo "primeira ``{`` até a última ``}``" falharia
    nesse caso). Resposta truncada, lista ou texto sem objeto devolvem ``None`` e seguem para o reparo.
    """
    candidates = [text.strip()]
    fenced = _FENCE.search(text)
    if fenced:
        candidates.append(fenced.group(1).strip())
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    decoder = json.JSONDecoder()
    for start in _top_level_starts(text):
        try:
            value, _ = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def format_validation_error(exc: ValidationError) -> str:
    """Resume um ``ValidationError`` em linhas ``campo: problema``, sem eco do valor recebido.

    O texto é devolvido ao modelo no reparo (ADR 0004). Omitir o valor evita reenviar conteúdo longo.
    """
    lines = []
    for error in exc.errors()[:MAX_REPAIR_ERRORS]:
        where = ".".join(str(part) for part in error["loc"]) or "(raiz)"
        lines.append(f"- {where}: {error['msg']}")
    extra = len(exc.errors()) - MAX_REPAIR_ERRORS
    if extra > 0:
        lines.append(f"- ... e mais {extra} erro(s)")
    return "\n".join(lines)
