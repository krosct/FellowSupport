"""Funções puras para tratar a saída bruta de um LLM: extrair o JSON e resumir erros de validação.

Ficam no domínio porque são regras sobre o formato da resposta, usadas tanto pelos adaptadores (que preenchem
``LLMResult.parsed``) quanto pelo serviço (que monta a mensagem de reparo).
"""

from __future__ import annotations

import json
import re

from pydantic import ValidationError

# Cerca de código Markdown que alguns modelos colocam em volta do JSON (```json ... ```).
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)

# Quantidade máxima de erros de validação devolvidos ao modelo no reparo (mantém o prompt curto).
MAX_REPAIR_ERRORS = 8


def extract_json_object(text: str) -> dict | None:
    """Extrai o primeiro objeto JSON do texto, ou ``None`` se não houver um objeto decodificável.

    Tenta, em ordem: o texto inteiro, o conteúdo de uma cerca de código e o trecho entre a primeira ``{`` e a
    última ``}``. A ordem prefere o caso limpo e só recorre à heurística quando o modelo "conversou" em volta.
    """
    candidates = [text.strip()]
    fenced = _FENCE.search(text)
    if fenced:
        candidates.append(fenced.group(1).strip())
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        candidates.append(text[start : end + 1])
    for candidate in candidates:
        try:
            value = json.loads(candidate)
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
