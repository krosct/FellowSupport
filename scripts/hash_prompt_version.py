"""Calcula o ``content_sha256`` de uma versão de prompt (ADR 0006), para preencher o ``meta.json`` ao criar a versão.

Uso: ``.venv/bin/python scripts/hash_prompt_version.py v1`` imprime o hash. Com ``--write``, grava o hash no
``meta.json`` somente se o campo ainda estiver vazio: versão publicada é imutável e nunca é reescrita por aqui.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.adapters.storage.prompt_files import FilePromptStore  # noqa: E402
from app.config import BASE_DIR  # noqa: E402
from app.domain.prompting.registry import META_FILE, PromptRegistry  # noqa: E402

# Valor de espaço reservado aceito como "ainda não calculado".
EMPTY_HASH = ""


def main() -> int:
    """Imprime o hash (e, com ``--write``, preenche o ``meta.json`` ainda sem hash)."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("version", help="versão da pasta prompts/, ex.: v1")
    parser.add_argument("--write", action="store_true", help="grava o hash se o meta.json ainda não tiver um")
    args = parser.parse_args()

    store = FilePromptStore(BASE_DIR / "prompts")
    digest = PromptRegistry(store).actual_sha256(args.version)
    print(digest)
    if args.write:
        meta_path = BASE_DIR / "prompts" / args.version / META_FILE
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("content_sha256", EMPTY_HASH) != EMPTY_HASH:
            print("meta.json já tem hash: versão imutável, nada foi gravado.", file=sys.stderr)
            return 1
        meta["content_sha256"] = digest
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
