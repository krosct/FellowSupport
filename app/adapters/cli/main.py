"""CLI do FellowSupport (argparse, stdlib). Execução: ``python -m app.adapters.cli.main <subcomando>``.

Subcomandos: ``profiles``, ``tickets``, ``versions`` e ``generate``. As Etapas seguintes acrescentam ``history``,
``compare`` etc.
Códigos de saída: 0 sucesso · 1 erro de uso ou validação · 2 não encontrado · 3 provedor de LLM indisponível.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import textwrap
from collections.abc import Sequence
from typing import NoReturn

from app.container import Container, build_container
from app.domain.errors import (
    DomainError,
    InvalidLLMOutput,
    LLMRateLimited,
    LLMUnavailable,
    NotFound,
    ValidationFailed,
)
from app.domain.models import Confidence, ContentType, Diagnosis, RunRecord
from app.services.generators import generate

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_NOT_FOUND = 2
EXIT_LLM = 3

# Tradução única erro do domínio -> código de saída (ADR 0018).
ERROR_EXIT_CODES: dict[type[DomainError], int] = {
    ValidationFailed: EXIT_USAGE,
    NotFound: EXIT_NOT_FOUND,
    LLMUnavailable: EXIT_LLM,
    LLMRateLimited: EXIT_LLM,
    InvalidLLMOutput: EXIT_LLM,
}

# Largura de quebra de linha ao imprimir textos longos (ticket, diagnóstico).
TEXT_WIDTH = 88

# Quantos caracteres do hash (SHA-256) mostrar na saída legível.
HASH_PREVIEW_CHARS = 12


class _Parser(argparse.ArgumentParser):
    """ArgumentParser que usa o código 1 para erros de uso (o 2 fica reservado a "não encontrado")."""

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(EXIT_USAGE, f"{self.prog}: erro: {message}\n")


def build_parser() -> argparse.ArgumentParser:
    """Monta o parser com os subcomandos disponíveis."""
    parser = _Parser(prog="fellowsupport", description="Assistente de suporte personalizado por perfil de cliente.")
    sub = parser.add_subparsers(dest="command", required=True, parser_class=_Parser, metavar="<comando>")

    profiles = sub.add_parser("profiles", help="lista os perfis de cliente do catálogo")
    profiles.add_argument("--id", help="mostra só o perfil com este id")
    profiles.add_argument("--json", action="store_true", help="saída em JSON")

    tickets = sub.add_parser("tickets", help="lista os tickets de exemplo do catálogo")
    tickets.add_argument("--id", help="mostra o ticket completo com este id")
    tickets.add_argument("--json", action="store_true", help="saída em JSON")

    versions = sub.add_parser("versions", help="lista as versões de prompt disponíveis")
    versions.add_argument("--json", action="store_true", help="saída em JSON")

    gen = sub.add_parser("generate", help="gera um conteúdo para um perfil e um ticket e salva a execução em JSON")
    gen.add_argument("--customer", required=True, metavar="ID", help="id do perfil (veja o comando profiles)")
    source = gen.add_mutually_exclusive_group(required=True)
    source.add_argument("--ticket", metavar="ID", help="id de um ticket do catálogo (veja o comando tickets)")
    source.add_argument("--text", help="texto livre do ticket")
    gen.add_argument(
        "--type", dest="content_type", default=ContentType.DIAGNOSIS.value,
        choices=[t.value for t in ContentType], help="tipo de conteúdo (padrão: diagnosis)",
    )
    gen.add_argument("--version", help="versão do prompt (padrão: DEFAULT_PROMPT_VERSION)")
    gen.add_argument("--json", action="store_true", help="saída em JSON")
    return parser


def _dump(data: object) -> None:
    """Imprime JSON legível, preservando a acentuação."""
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _cmd_profiles(container: Container, args: argparse.Namespace) -> None:
    """Lista (ou mostra um) perfil."""
    profiles = [container.profiles.get(args.id)] if args.id else container.profiles.list_all()
    if args.json:
        _dump([p.model_dump(mode="json") for p in profiles])
        return
    print(f"{'ID':<8} {'NOME':<12} {'NÍVEL':<14} {'ESTILO':<10} CANAL")
    for p in profiles:
        print(f"{p.id:<8} {p.name:<12} {p.tech_level.value:<14} {p.comm_style.value:<10} {p.channel.value}")


def _cmd_tickets(container: Container, args: argparse.Namespace) -> None:
    """Lista os tickets (id e título) ou mostra um completo com ``--id``."""
    if args.id:
        ticket = container.tickets.get(args.id)
        if args.json:
            _dump(ticket.model_dump(mode="json"))
        else:
            print(f"{ticket.id} · {ticket.title}\n")
            print(textwrap.fill(ticket.text, width=TEXT_WIDTH))
        return
    tickets = container.tickets.list_all()
    if args.json:
        _dump([t.model_dump(mode="json") for t in tickets])
        return
    for t in tickets:
        print(f"{t.id:<12} {t.title}")


def _cmd_versions(container: Container, args: argparse.Namespace) -> None:
    """Lista as versões de prompt com base, hash e descrição."""
    default = container.settings.default_prompt_version
    versions = container.prompts.versions()
    if args.json:
        _dump([{**v.model_dump(), "is_default": v.version == default} for v in versions])
        return
    print(f"{'VERSÃO':<8} {'BASE':<6} {'HASH':<{HASH_PREVIEW_CHARS}} DESCRIÇÃO")
    for v in versions:
        mark = " (padrão)" if v.version == default else ""
        print(f"{v.version:<8} {v.based_on or '-':<6} {v.content_sha256[:HASH_PREVIEW_CHARS]:<{HASH_PREVIEW_CHARS}} "
              f"{v.description}{mark}")


def _wrap(text: str, indent: str, marker: str = "") -> str:
    """Quebra ``text`` na largura da CLI; ``marker`` (ex.: ``"* "``) abre a 1ª linha e as demais alinham sob o texto."""
    return textwrap.fill(
        text, width=TEXT_WIDTH, initial_indent=indent + marker, subsequent_indent=indent + " " * len(marker)
    )


def _render_diagnosis(diagnosis: Diagnosis) -> str:
    """Diagnóstico em texto legível para o terminal (hipóteses, evidências, faltantes, conclusão e resumo)."""
    lines = ["HIPÓTESES"]
    for h in diagnosis.hypotheses:
        lines.append(_wrap(f"{h.description} ({h.probability_pct}%)", "  ", f"{h.id} · "))
        lines += [_wrap(text, "      ", "+ ") for text in h.evidence_for]
        lines += [_wrap(text, "      ", "- ") for text in h.evidence_against]
    lines += ["", "EVIDÊNCIAS DISPONÍVEIS"] + [_wrap(text, "  ", "* ") for text in diagnosis.available_evidence]
    lines += ["", "INFORMAÇÕES FALTANTES"]
    lines += [_wrap(f"{info.item}: {info.why_it_matters}", "  ", "* ") for info in diagnosis.missing_information]
    conclusion = diagnosis.probable_conclusion
    confidence = Confidence(conclusion.confidence).label
    lines += ["", f"CONCLUSÃO PROVÁVEL (confiança: {confidence})"]
    lines.append(_wrap(conclusion.summary, "  ", f"{conclusion.hypothesis_id} · "))
    lines += ["", "RESUMO PARA O CLIENTE", _wrap(diagnosis.customer_summary, "  ")]
    return "\n".join(lines)


def _render_run_header(record: RunRecord) -> str:
    """Cabeçalho da execução: cliente, ticket, versão do prompt, modelo, latência e tentativas."""
    profile = record.customer_profile
    return "\n".join([
        f"Cliente: {profile.name} ({profile.tech_level.value} · {profile.comm_style.value} · {profile.channel.value})",
        f"Ticket:  {record.ticket.title}",
        f"Prompt:  {record.prompt_version} (sha256 {record.prompt_sha256[:HASH_PREVIEW_CHARS]})",
        f"Modelo:  {record.model_used or record.model} via {record.provider} · {record.latency_ms} ms · "
        f"tentativas: {record.attempts}",
    ])


def _cmd_generate(container: Container, args: argparse.Namespace) -> None:
    """Gera o conteúdo pedido, imprime a saída legível (ou JSON) e o caminho do arquivo salvo."""
    result = generate(
        container.generation,
        content_type=ContentType(args.content_type),
        profile_id=args.customer,
        ticket_id=args.ticket,
        ticket_text=args.text,
        prompt_version=args.version,
    )
    record = result.record
    if args.json:
        _dump({"saved_path": result.saved_path, "run": record.model_dump(mode="json")})
        return
    print(_render_run_header(record))
    print()
    print(_render_diagnosis(Diagnosis.model_validate(record.output)))
    print()
    print(f"JSON salvo em: {result.saved_path}")


# Subcomando -> função que o executa.
_COMMANDS = {
    "profiles": _cmd_profiles,
    "tickets": _cmd_tickets,
    "versions": _cmd_versions,
    "generate": _cmd_generate,
}


def main(argv: Sequence[str] | None = None, container: Container | None = None) -> int:
    """Ponto de entrada. Devolve o código de saída em vez de chamar ``sys.exit`` (facilita os testes)."""
    args = build_parser().parse_args(argv)
    try:
        container = container or build_container()
        logging.basicConfig(level=container.settings.log_level, format="%(levelname)s %(name)s: %(message)s")
        _COMMANDS[args.command](container, args)
    except DomainError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return next((code for cls, code in ERROR_EXIT_CODES.items() if isinstance(exc, cls)), EXIT_USAGE)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
