"""Teste de fumaça REAL e manual contra o provedor de LLM (fora do pytest, ADR 0016).

Faz **uma** chamada ao modelo com o prompt real do diagnóstico e confere: JSON válido, saída aceita pelo schema,
português do Brasil (heurística por palavras funcionais), latência e uso de tokens. Serve para validar um
modelo candidato antes de adotá-lo como padrão (ADR 0026).

Cuidados com cota e segredo:
- uma execução = uma chamada: sem reparo e, por padrão, sem retentativas do SDK (``--retries 0``), para a
  contagem de chamadas ser exata; cada chamada é anotada em ``var/smoke/calls.log``;
- a chave vem do ``.env`` e nunca é impressa; sem chave ou com ``LLM_PROVIDER=fake`` o script avisa que o teste
  real está bloqueado e sai com código 2 (use ``--fake`` para ensaiar o script sem rede).

Uso: ``.venv/bin/python scripts/smoke_llm.py [--model ID] [--mode json_schema|json_object|prompt]``
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import get_args

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import ValidationError  # noqa: E402

from app.adapters.llm.fake import FakeLLM  # noqa: E402
from app.adapters.llm.openai_compat import OpenAICompatClient  # noqa: E402
from app.adapters.storage.json_files import JsonProfileRepo, JsonTicketRepo  # noqa: E402
from app.adapters.storage.prompt_files import FilePromptStore  # noqa: E402
from app.config import Settings  # noqa: E402
from app.domain.errors import DomainError  # noqa: E402
from app.domain.llm_output import format_validation_error  # noqa: E402
from app.domain.models import ContentType, Diagnosis  # noqa: E402
from app.domain.prompting.engine import PromptBuilder  # noqa: E402
from app.domain.prompting.registry import PromptRegistry  # noqa: E402
from app.ports.llm import LLMParams, ReasoningMode  # noqa: E402

EXIT_OK, EXIT_FAILED, EXIT_BLOCKED = 0, 1, 2

# Pastas e arquivos de saída do smoke (dentro de DATA_DIR, que é ignorado pelo git).
SMOKE_DIR = "smoke"
CALLS_LOG = "calls.log"

# Palavras funcionais usadas na heurística de idioma. Não detectam qualidade, só pegam resposta em outro idioma.
PT_WORDS = set("de a o que e do da em um para com não uma os no se na por mais as dos como mas foi ao ele das tem "
               "à seu sua ou ser quando muito há nos já está eu também só pelo pela até isso ela entre era depois "
               "sem mesmo aos ter seus quem nas me esse eles estão você tinha foram essa num nem suas meu às "
               "minha têm numa pelos elas havia seja qual será nós".split())
EN_WORDS = set("the of and to in is that it for with as on was are this be by not from at or an have has but "
               "you they their which can will if there been would about more".split())
# Fração mínima de palavras funcionais em português entre as reconhecidas (pt + en).
MIN_PT_SHARE = 0.8


def _strings(value: object) -> list[str]:
    """Todos os textos de um JSON aninhado (valores, não chaves)."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return []


def language_check(output: dict) -> dict:
    """Mede a fração de palavras funcionais em português e a presença de acentos nos textos da saída."""
    text = " ".join(_strings(output)).lower()
    words = re.findall(r"[a-zà-ú]+", text)
    pt = sum(w in PT_WORDS for w in words)
    en = sum(w in EN_WORDS for w in words)
    share = pt / (pt + en) if pt + en else 0.0
    return {"words": len(words), "pt_function_words": pt, "en_function_words": en, "pt_share": round(share, 3),
            "has_accents": bool(re.search(r"[à-ú]", text)), "ok": share >= MIN_PT_SHARE}


def main() -> int:
    """Executa uma chamada, imprime o relatório e devolve o código de saída."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", help="modelo a testar (padrão: LLM_MODEL do .env)")
    parser.add_argument("--mode", choices=["json_schema", "json_object", "prompt"], help="modo estruturado")
    parser.add_argument("--profile", default="marta", help="id do perfil (padrão: marta)")
    parser.add_argument("--ticket", default="t-2fa", help="id do ticket (padrão: t-2fa)")
    parser.add_argument("--version", help="versão do prompt (padrão: DEFAULT_PROMPT_VERSION)")
    parser.add_argument("--reasoning", choices=get_args(ReasoningMode), help="raciocínio (padrão: LLM_REASONING)")
    parser.add_argument("--max-tokens", type=int, help="limite de tokens da resposta (padrão: LLM_MAX_TOKENS)")
    parser.add_argument("--retries", type=int, default=0, help="retentativas do SDK em 429/5xx (padrão: 0)")
    parser.add_argument("--fake", action="store_true", help="usa o provedor fake (ensaia o script, sem rede)")
    args = parser.parse_args()

    settings = Settings()
    key = settings.openrouter_api_key.get_secret_value()
    if not args.fake and (settings.llm_provider != "openrouter" or not key):
        print("BLOQUEADO: o teste real exige LLM_PROVIDER=openrouter e OPENROUTER_API_KEY no .env.")
        print("Use --fake para ensaiar o script sem rede.")
        return EXIT_BLOCKED

    model = args.model or settings.llm_model
    mode = args.mode or settings.llm_structured_mode
    version = args.version or settings.default_prompt_version
    registry = PromptRegistry(FilePromptStore(settings.prompts_dir))
    profile = JsonProfileRepo(settings.catalog_dir).get(args.profile)
    ticket = JsonTicketRepo(settings.catalog_dir).get(args.ticket)
    messages = PromptBuilder(registry).build(version, ContentType.DIAGNOSIS, profile, ticket.text)
    params = LLMParams(
        model=model,
        temperature=settings.llm_temperature,
        max_tokens=args.max_tokens or settings.llm_max_tokens,
        structured_mode=mode,
        reasoning=args.reasoning or settings.llm_reasoning,
    )
    client = FakeLLM() if args.fake else OpenAICompatClient(
        api_key=key, base_url=settings.llm_base_url, timeout_s=settings.llm_timeout_s, max_retries=args.retries
    )

    print(f"Modelo: {model} · modo: {mode} · raciocínio: {params.reasoning} · prompt {version} · "
          f"perfil {profile.id} · ticket {ticket.id}")
    smoke_dir = settings.data_dir / SMOKE_DIR
    smoke_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone()
    report: dict = {
        "timestamp": stamp.isoformat(timespec="seconds"), "model": model, "mode": mode, "prompt_version": version,
        "max_tokens": params.max_tokens, "reasoning": params.reasoning, "profile": profile.id,
        "ticket": ticket.id, "fake": args.fake,
    }
    try:
        result = client.complete(messages, Diagnosis, params)
    except DomainError as exc:
        report.update(outcome="provider_error", error=f"{type(exc).__name__}: {exc}")
        _log_call(smoke_dir, report)
        print(f"FALHA DO PROVEDOR: {type(exc).__name__}: {exc}")
        return EXIT_FAILED

    report.update(model_used=result.model_used, latency_ms=result.latency_ms, usage=result.usage,
                  raw_text=result.text)
    json_ok = result.parsed is not None
    schema_ok, problem = False, "sem JSON"
    if json_ok:
        try:
            Diagnosis.model_validate(result.parsed)
            schema_ok, problem = True, ""
        except ValidationError as exc:
            problem = format_validation_error(exc)
    language = language_check(result.parsed) if json_ok else {"ok": False}
    report.update(json_ok=json_ok, schema_ok=schema_ok, schema_problem=problem, language=language,
                  outcome="ok" if schema_ok and language["ok"] else "invalid")
    _log_call(smoke_dir, report)

    print(f"Modelo efetivo: {result.model_used} · latência: {result.latency_ms} ms · uso: {result.usage}")
    print(f"JSON válido: {json_ok} · schema válido: {schema_ok} · pt-BR: {language}")
    if problem:
        print(f"Problema do schema:\n{problem}")
    if json_ok:
        print(json.dumps(result.parsed, ensure_ascii=False, indent=2))
    else:
        print(f"Texto bruto:\n{result.text[:1500]}")
    out_file = smoke_dir / f"{stamp.strftime('%Y%m%dT%H%M%S')}_{model.replace('/', '_').replace(':', '_')}.json"
    out_file.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Relatório salvo em: {out_file}")
    return EXIT_OK if report["outcome"] == "ok" else EXIT_FAILED


def _log_call(smoke_dir: Path, report: dict) -> None:
    """Anota uma linha por chamada em ``calls.log`` (orçamento de chamadas reais)."""
    if report.get("fake"):
        return
    line = (f"{report['timestamp']}\t{report['model']}\t{report['mode']}\treasoning={report['reasoning']}"
            f"\t{report['outcome']}\n")
    with (smoke_dir / CALLS_LOG).open("a", encoding="utf-8") as log:
        log.write(line)


if __name__ == "__main__":
    raise SystemExit(main())
