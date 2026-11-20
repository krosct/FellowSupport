"""CLI do FellowSupport (argparse, stdlib). Execução: ``python -m app.adapters.cli.main <subcomando>``.

Subcomandos: ``profiles``, ``tickets``, ``versions`` e ``generate`` (``--type`` com os quatro tipos ou ``all``;
``--no-cache`` ignora o cache). As Etapas seguintes acrescentam ``compare`` etc.
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

from app.adapters.cli.render import HASH_PREVIEW_CHARS, TEXT_WIDTH, render_output, render_run_header
from app.container import Container, build_container
from app.domain.errors import (
    DomainError,
    InvalidLLMOutput,
    LLMRateLimited,
    LLMUnavailable,
    NotFound,
    ValidationFailed,
)
from app.domain.models import ALL_OPTION_VALUE, ContentType
from app.services.generators import generate, generate_all

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
        choices=[*(t.value for t in ContentType), ALL_OPTION_VALUE],
        help="tipo de conteúdo; 'all' gera os quatro em paralelo (padrão: diagnosis)",
    )
    gen.add_argument("--version", help="versão do prompt (padrão: DEFAULT_PROMPT_VERSION)")
    gen.add_argument(
        "--no-cache", action="store_true", help="ignora o cache: gera de novo e não lê nem grava o cache"
    )
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


def _exit_code(exc: DomainError) -> int:
    """Código de saída de uma exceção do domínio (ADR 0018)."""
    return next((code for cls, code in ERROR_EXIT_CODES.items() if isinstance(exc, cls)), EXIT_USAGE)


def _cmd_generate_all(container: Container, args: argparse.Namespace) -> int:
    """Gera os quatro tipos em paralelo e imprime um bloco por tipo, com o caminho do JSON de cada execução.

    Se algum tipo falhar, os demais são impressos mesmo assim e o código de saída é o da primeira falha.
    """
    batch = generate_all(
        container.generation,
        profile_id=args.customer,
        ticket_id=args.ticket,
        ticket_text=args.text,
        prompt_version=args.version,
        use_cache=not args.no_cache,
    )
    if args.json:
        _dump({"results": [
            {
                "content_type": item.content_type.value,
                "saved_path": item.result.saved_path if item.result else None,
                "run": item.result.record.model_dump(mode="json") if item.result else None,
                "error": {"type": type(item.error).__name__, "message": str(item.error)} if item.error else None,
            }
            for item in batch.items
        ]})
    else:
        first_ok = next((item.result.record for item in batch.items if item.ok), None)
        if first_ok is not None:
            print(render_run_header(first_ok))
        for item in batch.items:
            print(f"\n{'=' * TEXT_WIDTH}\n{item.content_type.label.upper()}\n{'=' * TEXT_WIDTH}")
            if item.ok:
                print(render_output(item.result.record))
                print(f"\nJSON salvo em: {item.result.saved_path}")
            else:
                print(f"FALHOU: {item.error}")
                if item.result:
                    print(f"JSON de erro salvo em: {item.result.saved_path}")
    for exc in batch.errors:
        print(f"erro: {exc}", file=sys.stderr)
    return _exit_code(batch.errors[0]) if batch.errors else EXIT_OK


def _cmd_generate(container: Container, args: argparse.Namespace) -> int | None:
    """Gera o conteúdo pedido, imprime a saída legível (ou JSON) e o caminho do arquivo salvo."""
    if args.content_type == ALL_OPTION_VALUE:
        return _cmd_generate_all(container, args)
    result = generate(
        container.generation,
        content_type=ContentType(args.content_type),
        profile_id=args.customer,
        ticket_id=args.ticket,
        ticket_text=args.text,
        prompt_version=args.version,
        use_cache=not args.no_cache,
    )
    record = result.record
    if args.json:
        _dump({"saved_path": result.saved_path, "run": record.model_dump(mode="json")})
        return None
    print(render_run_header(record))
    print()
    print(render_output(record))
    print()
    print(f"JSON salvo em: {result.saved_path}")
    return None


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
        return _COMMANDS[args.command](container, args) or EXIT_OK
    except DomainError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return _exit_code(exc)


if __name__ == "__main__":
    raise SystemExit(main())
