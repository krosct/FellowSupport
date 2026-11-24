"""Calcula o ``content_sha256`` de uma versão de prompt (ADR 0006), para preencher o ``meta.json`` ao criar a versão.

Uso: ``.venv/bin/python -m scripts.hash_prompt_version v1`` imprime o hash. Com ``--write``, grava o hash no
``meta.json`` somente se o campo ainda estiver vazio: versão publicada é imutável e nunca é reescrita por aqui.
"""

import argparse
import json
import sys

from app.adapters.storage.prompt_files import FilePromptStore
from app.config import BASE_DIR
from app.domain.prompting.registry import META_FILE, PromptRegistry

# Valor de espaço reservado aceito como "ainda não calculado".
EMPTY_HASH = ""


def main() -> int:
    """Imprime o hash (e, com ``--write``, preenche o ``meta.json`` ainda sem hash)."""
    # Configura e lê os argumentos de linha de comando.
    parser = argparse.ArgumentParser(description=str(__doc__).splitlines()[0])
    parser.add_argument("version", help="versão da pasta prompts/, ex.: v1")
    parser.add_argument("--write", action="store_true", help="grava o hash se o meta.json ainda não tiver um")
    args = parser.parse_args()

    # Calcula e imprime o hash SHA-256 da pasta de prompts.
    root = BASE_DIR / "prompts"
    digest = PromptRegistry(FilePromptStore(root)).actual_sha256(args.version)
    print(digest)
    # Com --write, grava o hash no meta.json somente se ainda estiver vazio.
    if args.write:
        meta_path = root / args.version / META_FILE
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("content_sha256", EMPTY_HASH) != EMPTY_HASH:
            print("meta.json já tem hash: versão imutável, nada foi gravado.", file=sys.stderr)
            return 1
        meta["content_sha256"] = digest
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
