"""CLI do FellowSupport (argparse, stdlib). Execução: ``python -m app.adapters.cli.main <subcomando>``.

Etapa 0: ``profiles`` e ``tickets``. As Etapas seguintes acrescentam ``generate``, ``history``, ``compare`` etc.
Códigos de saída: 0 sucesso · 1 erro de uso ou validação · 2 não encontrado · 3 provedor de LLM indisponível.
"""

from __future__ import annotations

import argparse
import json
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

# Largura de quebra de linha ao imprimir o texto de um ticket.
TEXT_WIDTH = 88


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


# Subcomando -> função que o executa.
_COMMANDS = {"profiles": _cmd_profiles, "tickets": _cmd_tickets}


def main(argv: Sequence[str] | None = None, container: Container | None = None) -> int:
    """Ponto de entrada. Devolve o código de saída em vez de chamar ``sys.exit`` (facilita os testes)."""
    args = build_parser().parse_args(argv)
    try:
        _COMMANDS[args.command](container or build_container(), args)
    except DomainError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return next((code for cls, code in ERROR_EXIT_CODES.items() if isinstance(exc, cls)), EXIT_USAGE)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
