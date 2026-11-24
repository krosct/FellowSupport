"""CLI do FellowSupport (argparse, stdlib). Execução: ``python -m app.adapters.cli.main <subcomando>``.

Adaptador de entrada direto (no mesmo nível da API HTTP, ADR 0002 e ADR 0041): executa os casos de uso do núcleo
diretamente via ``Container`` e ``app/services/``, sem depender de servidor nem de FastAPI. Assim, CLI e API
compartilham exatamente as mesmas regras de negócio, validação, cache e persistência:

- ``meta``: metadados públicos (provedor, versão padrão, tipos, rubrica e limites);
- ``customer`` e ``ticket`` com ``list``, ``create``, ``update`` e ``delete`` consultam e editam o catálogo
  (ADR 0037);
- ``prompt`` com ``list``, ``create`` e ``delete`` lista e gerencia versões imutáveis de prompt (``list --details``
  mostra o que mudou em cada versão derivada);
- ``generate`` (``--type`` com os quatro tipos ou ``all``; ``--no-cache`` não consulta o cache);
- ``history`` com ``generation`` (tabela paginada de execuções com filtros) e ``comparison`` (lista paginada por
  padrão, ou ``list`` e ``show <id>``), espelhando as duas visões da aba Histórico do site;
- ``show <id>``: mostra uma execução salva pelo id, como o ``generate`` a mostrou;
- ``compare <ids>``: compara execuções que já existem, uma por versão (não gera nada); se já houver comparação
  dessas execuções, pergunta se carrega a salva ou faz outra do zero; avalia e salva.

Códigos de saída: 0 sucesso · 1 erro de uso ou validação · 2 não encontrado · 3 provedor de LLM indisponível,
limite de chamadas ou saída inválida.
"""

import argparse
import json
import sys
import textwrap
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import NoReturn, get_args

from app.adapters.cli.render import (
    TEXT_WIDTH,
    render_comparison,
    render_comparisons_table,
    render_customers_table,
    render_history_table,
    render_meta,
    render_output,
    render_page_info,
    render_prompt_detail,
    render_run_header,
    render_scale,
    render_scenario_header,
    render_stored_run,
    render_tickets_table,
    render_version_changes,
    render_version_header,
    render_versions,
)
from app.container import Container, build_container
from app.domain import rubric
from app.domain.errors import (
    CacheReplaceRequired,
    DomainError,
    Forbidden,
    InvalidLLMOutput,
    LLMRateLimited,
    LLMUnavailable,
    NotFound,
    Unauthorized,
    ValidationFailed,
)
from app.domain.models import (
    ALL_OPTION_VALUE,
    Channel,
    CommStyle,
    ContentType,
    RunRecord,
    RunStatus,
    TechLevel,
    Ticket,
)
from app.domain.prompting.registry import BASE_PROMPT_VERSION, META_FILE, PromptChange
from app.ports.repositories import StoredComparison, StoredRun
from app.services.catalog import (
    create_profile,
    create_ticket,
    delete_profile,
    delete_ticket,
    update_profile,
    update_ticket,
)
from app.services.comparison import (
    find_saved_comparison,
    get_comparison,
    list_comparisons,
    load_comparable_runs,
    save_comparison,
    summarize_comparison,
)
from app.services.generators import generate, generate_all
from app.services.history import (
    DEFAULT_HISTORY_LIMIT,
    PAGE_SIZES,
    HistoryFilters,
    Page,
    get_run,
    list_runs,
    summarize_run,
)
from app.services.meta import build_meta, list_prompt_versions
from app.services.prompts import create_prompt, delete_prompt, get_prompt

# Flag que confirma a substituição de entradas do cache quando ``--no-cache`` as trocaria (ADR 0036).
CONFIRM_REPLACE_FLAG = "--confirm-replace"

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_NOT_FOUND = 2
EXIT_LLM = 3

# Tradução única erro do domínio -> código de saída da CLI (ADR 0018 e ADR 0041).
ERROR_EXIT_CODES: dict[type[DomainError], int] = {
    Unauthorized: EXIT_USAGE,
    Forbidden: EXIT_USAGE,
    NotFound: EXIT_NOT_FOUND,
    CacheReplaceRequired: EXIT_USAGE,
    ValidationFailed: EXIT_USAGE,
    LLMRateLimited: EXIT_LLM,
    InvalidLLMOutput: EXIT_LLM,
    LLMUnavailable: EXIT_LLM,
}

# Respostas das perguntas de sim/não e da escolha "carregar ou comparar de novo" (sem diferenciar maiúsculas).
YES_ANSWERS = ("s", "sim")
LOAD_ANSWERS = ("c", "carregar")
NEW_ANSWERS = ("n", "nova")


class _Parser(argparse.ArgumentParser):
    """ArgumentParser que usa o código 1 para erros de uso (o 2 fica reservado a "não encontrado")."""

    def error(self, message: str) -> NoReturn:
        """Imprime o uso e sai com ``EXIT_USAGE`` (o argparse padrão sairia com 2)."""
        self.print_usage(sys.stderr)
        self.exit(EXIT_USAGE, f"{self.prog}: erro: {message}\n")


def _add_json(parser: argparse.ArgumentParser, *, suppress_default: bool = False) -> None:
    """Acrescenta ``--json`` (imprime o resultado estruturado em JSON)."""
    kwargs: dict[str, object] = {"default": argparse.SUPPRESS} if suppress_default else {}
    parser.add_argument("--json", action="store_true", help="saída em JSON", **kwargs)


def _add_confirm_replace(parser: argparse.ArgumentParser) -> None:
    """Acrescenta ``--confirm-replace``: confirma de antemão a troca de entradas do cache (ADR 0036)."""
    parser.add_argument(
        CONFIRM_REPLACE_FLAG, action="store_true", dest="confirm_replace",
        help="com --no-cache, confirma a substituição de entradas do cache (sem ela, o comando lista e não gera)",
    )


def _add_page(parser: argparse.ArgumentParser, noun: str, *, suppress_default: bool = False) -> None:
    """Acrescenta ``--page`` e ``--limit``; os tamanhos aceitos são os do domínio (``PAGE_SIZES``)."""
    page_default = argparse.SUPPRESS if suppress_default else 1
    limit_kwargs: dict[str, object] = {"default": argparse.SUPPRESS} if suppress_default else {}
    parser.add_argument("--page", type=int, default=page_default, metavar="N", help="número da página (padrão 1)")
    parser.add_argument(
        "--limit",
        type=int,
        metavar="N",
        help=f"{noun} por página (tamanhos aceitos: {', '.join(map(str, PAGE_SIZES))})",
        **limit_kwargs,
    )


def _add_customer_fields(parser: argparse.ArgumentParser, required: bool) -> None:
    """Campos do cliente: nome, nível técnico, estilo e canal (valores dos enums do domínio)."""
    parser.add_argument("--name", required=required, help="nome do cliente")
    for flag, enum_cls, label in (
        ("--tech-level", TechLevel, "nível técnico"), ("--comm-style", CommStyle, "estilo de comunicação"),
        ("--channel", Channel, "canal"),
    ):
        parser.add_argument(flag, required=required, choices=[item.value for item in enum_cls], help=label)


def _add_ticket_fields(parser: argparse.ArgumentParser, required: bool) -> None:
    """Campos do ticket: título e corpo."""
    parser.add_argument("--title", required=required, help="título do ticket")
    parser.add_argument("--text", required=required, help="corpo do ticket (o relato do cliente)")


def _add_prompt_fields(parser: argparse.ArgumentParser) -> None:
    """Campos de criação de prompt: versão base, descrição, mudanças e ajustes de arquivos."""
    parser.add_argument(
        "--based-on", required=True, metavar="VERSÃO", help="versão base (source) obrigatória, ex.: v1"
    )
    parser.add_argument("--description", required=True, help="descrição da versão do prompt")
    parser.add_argument(
        "--changes", metavar="ARQ_OU_JSON",
        help='mudanças em JSON (caminho de arquivo ou texto): [{"what": ..., "why": ..., "expected_effect": ...}]',
    )
    parser.add_argument("--what", help="o que mudou (atalho para 1 mudança; exige --why e --expected-effect)")
    parser.add_argument("--why", help="por que mudou")
    parser.add_argument("--expected-effect", help="efeito esperado na rubrica")
    parser.add_argument(
        "--file", dest="file_maps", action="append", default=[], metavar="NOME=CAMINHO",
        help="define/substitui um arquivo lendo o conteúdo de CAMINHO (pode repetir)",
    )
    parser.add_argument(
        "--set", dest="inline_files", action="append", default=[], metavar="NOME=TEXTO",
        help="define/substitui um arquivo com texto direto (pode repetir)",
    )
    parser.add_argument(
        "--files-dir", type=Path, metavar="PASTA",
        help="carrega os arquivos de prompt desta pasta (exceto meta.json)",
    )
    parser.add_argument(
        "--remove-file", dest="remove_files", action="append", default=[], metavar="NOME",
        help="remove um arquivo da versão (pode repetir)",
    )


def _add_catalog_crud(
    sub: argparse._SubParsersAction, name: str, noun: str, plural: str, id_help: str, add_fields: Callable
) -> None:
    """Subcomando ``<name> list|create|update|delete`` para um cadastro do catálogo (clientes ou tickets)."""
    command = sub.add_parser(name, help=f"lista, cria, edita ou remove {plural} do catálogo")
    actions = command.add_subparsers(dest="action", required=True, parser_class=_Parser, metavar="<ação>")
    list_cmd = actions.add_parser("list", help=f"lista os {plural} do catálogo")
    list_cmd.add_argument("--id", help=id_help)
    _add_json(list_cmd)
    create = actions.add_parser("create", help=f"cria um {noun} (o id é gerado automaticamente)")
    add_fields(create, required=True)
    _add_json(create)
    update = actions.add_parser("update", help=f"edita um {noun}; os campos omitidos ficam como estão")
    update.add_argument("item_id", metavar="ID", help=f"id do {noun}")
    add_fields(update, required=False)
    _add_json(update)
    delete = actions.add_parser("delete", help=f"remove um {noun} (o histórico de execuções não muda)")
    delete.add_argument("item_id", metavar="ID", help=f"id do {noun}")
    delete.add_argument("--yes", action="store_true", help="confirma a remoção sem perguntar")
    _add_json(delete)


def build_parser() -> argparse.ArgumentParser:
    """Monta o parser com os subcomandos disponíveis."""
    # Cria o parser raiz e registra todos os subcomandos da CLI.
    parser = _Parser(prog="fellowsupport", description="Assistente de suporte personalizado por perfil de cliente.")
    sub = parser.add_subparsers(dest="command", required=True, parser_class=_Parser, metavar="<comando>")

    meta = sub.add_parser("meta", help="provedor, versão padrão, tipos de conteúdo, rubrica e limites")
    _add_json(meta)

    _add_catalog_crud(
        sub, "customer", "cliente", "clientes", "mostra só o cliente com este id", _add_customer_fields
    )
    _add_catalog_crud(
        sub, "ticket", "ticket", "tickets", "mostra o ticket completo com este id", _add_ticket_fields
    )

    prompt = sub.add_parser("prompt", help="lista, cria ou remove versões de prompt")
    prompt_actions = prompt.add_subparsers(dest="action", required=True, parser_class=_Parser, metavar="<ação>")
    prompt_list = prompt_actions.add_parser("list", help="lista as versões de prompt (ou mostra uma com --id)")
    prompt_list.add_argument("--id", help="mostra os detalhes completos desta versão (ex.: v1)")
    prompt_list.add_argument("--details", action="store_true", help="mostra o que mudou em cada versão derivada")
    _add_json(prompt_list)
    prompt_create = prompt_actions.add_parser(
        "create", help="cria uma versão nova a partir de uma versão base (--based-on) e calcula o hash"
    )
    _add_prompt_fields(prompt_create)
    _add_json(prompt_create)
    prompt_delete = prompt_actions.add_parser("delete", help="remove uma versão derivada (v1 não pode ser removida)")
    prompt_delete.add_argument("version_id", metavar="VERSÃO", help="versão a remover (ex.: v2)")
    prompt_delete.add_argument("--yes", action="store_true", help="confirma a remoção sem perguntar")
    _add_json(prompt_delete)

    gen = sub.add_parser("generate", help="gera um conteúdo para um cliente e um ticket e salva a execução em JSON")
    gen.add_argument("--customer", required=True, metavar="ID", help="id do cliente (veja o comando customer list)")
    gen.add_argument("--ticket", required=True, metavar="ID", help="id do ticket (veja o comando ticket list)")
    gen.add_argument(
        "--type", dest="content_type", default=ContentType.DIAGNOSIS.value,
        choices=[*(t.value for t in ContentType), ALL_OPTION_VALUE],
        help="tipo de conteúdo; 'all' gera os quatro em paralelo (padrão: diagnosis)",
    )
    gen.add_argument("--version", help="versão do prompt (padrão: a mais nova)")
    gen.add_argument(
        "--no-cache", action="store_true", help="não consulta o cache: gera de novo e grava o resultado no cache"
    )
    _add_confirm_replace(gen)
    _add_json(gen)

    history = sub.add_parser("history", help="lista as execuções e comparações salvas")
    history_sub = history.add_subparsers(
        dest="history_command", required=True, parser_class=_Parser, metavar="<subcomando>"
    )

    generation = history_sub.add_parser(
        "generation", help="lista as execuções salvas, da mais recente para a mais antiga"
    )
    generation.add_argument("--customer", metavar="ID", help="só execuções deste cliente")
    generation.add_argument("--ticket", metavar="ID", help="só execuções deste ticket")
    generation.add_argument(
        "--type", dest="content_type", choices=[t.value for t in ContentType], help="só execuções deste tipo"
    )
    generation.add_argument("--version", help="só execuções desta versão de prompt")
    generation.add_argument("--status", choices=get_args(RunStatus), help="só execuções com este status")
    generation.add_argument(
        "--cache-key", metavar="CHAVE",
        help="só execuções com esta chave de cache (ou o começo dela): as equivalentes entre si",
    )
    _add_page(generation, "execuções")
    _add_json(generation)

    comparison = history_sub.add_parser("comparison", help="lista ou mostra comparações salvas")
    _add_page(comparison, "comparações")
    _add_json(comparison)
    comparison_sub = comparison.add_subparsers(
        dest="comparison_command", required=False, parser_class=_Parser, metavar="[<ação>]"
    )
    comparison_list = comparison_sub.add_parser(
        "list", help="lista as comparações salvas, da mais recente para a mais antiga"
    )
    _add_page(comparison_list, "comparações", suppress_default=True)
    _add_json(comparison_list, suppress_default=True)
    comparison_show = comparison_sub.add_parser("show", help="mostra uma comparação salva pelo id")
    comparison_show.add_argument(
        "comparison_id", metavar="ID", help="id da comparação (veja o comando history comparison)"
    )
    _add_json(comparison_show, suppress_default=True)

    show = sub.add_parser("show", help="mostra uma execução salva pelo id, como o generate a mostrou")
    show.add_argument("run_id", metavar="ID", help="id da execução (veja o comando history generation)")
    _add_json(show)

    compare = sub.add_parser(
        "compare",
        help="compara execuções já feitas (uma por versão, mesmo cenário), avalia e salva; não gera nada",
    )
    compare.add_argument(
        "run_ids", nargs="+", metavar="ID",
        help="ids das execuções (2 ou mais, de versões diferentes; veja history generation --status ok)",
    )
    choice = compare.add_mutually_exclusive_group()
    choice.add_argument(
        "--load", action="store_true", help="se já houver comparação destas execuções, mostra a salva"
    )
    choice.add_argument(
        "--new", action="store_true", help="se já houver comparação destas execuções, faz outra do zero"
    )
    compare.add_argument(
        "--evaluations", type=Path, metavar="ARQ.json",
        help='notas sem perguntar: {"<id>": {"clarity": {"score": 4, "justification": "..."}, ...}, ...}',
    )
    compare.add_argument("--conclusion", metavar="TEXTO", help="conclusão do candidato (opcional)")
    _add_json(compare)
    return parser


def _dump(data: object) -> None:
    """Imprime JSON legível, preservando a acentuação."""
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _ask(prompt: str, missing_hint: str) -> str:
    """Pergunta no terminal; sem terminal (stdin fechado), falha dizendo o que informar em vez de travar."""
    try:
        return input(prompt).strip()
    except EOFError:
        print()  # fecha a linha do prompt que ficou sem resposta
        raise ValidationFailed(f"Sem terminal interativo para responder: {missing_hint}") from None


def _run_payload(stored: StoredRun) -> dict:
    """Payload JSON de uma execução salva (mesmo contrato de ``GenerateOut`` / ``RunDetailOut``)."""
    return {"saved_path": stored.saved_path, "run": stored.record.model_dump(mode="json")}


def _comparison_payload(stored: StoredComparison) -> dict:
    """Payload JSON de uma comparação salva (mesmo contrato de ``ComparisonOut``)."""
    return {"saved_path": stored.saved_path, "comparison": stored.record.model_dump(mode="json")}


# --- metadados e catálogo ------------------------------------------------------------------------------------


def _cmd_meta(container: Container, args: argparse.Namespace) -> None:
    """Mostra os metadados públicos do app."""
    settings = container.settings
    meta_dict = build_meta(
        provider=settings.llm_provider,
        model=settings.llm_model,
        max_ticket_chars=settings.max_ticket_chars,
        registry=container.prompts,
    ).model_dump(mode="json")
    if args.json:
        _dump(meta_dict)
    else:
        print(render_meta(meta_dict))


def _list_customers(container: Container, args: argparse.Namespace) -> None:
    """Lista (ou mostra um) cliente."""
    customers = [container.profiles.get(args.id)] if args.id else container.profiles.list_all()
    if args.json:
        _dump([c.model_dump(mode="json") for c in customers])
        return
    print(render_customers_table(customers))


def _print_ticket(ticket: Ticket) -> None:
    """Ticket completo: id, título e corpo quebrado na largura do terminal."""
    print(f"{ticket.id} · {ticket.title}\n")
    print(textwrap.fill(ticket.text, width=TEXT_WIDTH))


def _list_tickets(container: Container, args: argparse.Namespace) -> None:
    """Lista os tickets (id e título) ou mostra um completo com ``--id``."""
    if args.id:
        ticket = container.tickets.get(args.id)
        if args.json:
            _dump(ticket.model_dump(mode="json"))
        else:
            _print_ticket(ticket)
        return
    tickets = container.tickets.list_all()
    if args.json:
        _dump([t.model_dump(mode="json") for t in tickets])
        return
    print(render_tickets_table(tickets))


def _confirm_delete(args: argparse.Namespace, what: str) -> bool:
    """Confirma a remoção; ``--yes`` dispensa a pergunta."""
    if args.yes:
        return True
    answer = _ask(f"Remover {what}? (s/N): ", "use --yes para confirmar a remoção.")
    return answer.lower() in YES_ANSWERS


def _cmd_customer(container: Container, args: argparse.Namespace) -> None:
    """``customer list|create|update|delete`` usando os casos de uso de ``services/catalog``."""
    if args.action == "list":
        _list_customers(container, args)
        return
    if args.action == "create":
        customer = create_profile(
            container.profiles,
            args.name,
            TechLevel(args.tech_level),
            CommStyle(args.comm_style),
            Channel(args.channel),
        )
        verb = "criado"
    else:
        current = container.profiles.get(args.item_id)
        if args.action == "update":
            customer = update_profile(
                container.profiles,
                args.item_id,
                args.name if args.name is not None else current.name,
                TechLevel(args.tech_level) if args.tech_level is not None else current.tech_level,
                CommStyle(args.comm_style) if args.comm_style is not None else current.comm_style,
                Channel(args.channel) if args.channel is not None else current.channel,
            )
            verb = "atualizado"
        elif _confirm_delete(args, f"o cliente {current.name} ({current.id})"):
            customer, verb = delete_profile(container.profiles, args.item_id), "removido"
        else:
            print("Remoção cancelada.")
            return
    if args.json:
        _dump(customer.model_dump(mode="json"))
        return
    print(f"Cliente {verb}:")
    print(render_customers_table([customer]))


def _cmd_ticket(container: Container, args: argparse.Namespace) -> None:
    """``ticket list|create|update|delete`` usando os casos de uso de ``services/catalog``."""
    if args.action == "list":
        _list_tickets(container, args)
        return
    max_chars = container.settings.max_ticket_chars
    if args.action == "create":
        ticket = create_ticket(container.tickets, args.title, args.text, max_chars)
        verb = "criado"
    else:
        current = container.tickets.get(args.item_id)
        if args.action == "update":
            ticket = update_ticket(
                container.tickets,
                args.item_id,
                args.title if args.title is not None else current.title,
                args.text if args.text is not None else current.text,
                max_chars,
            )
            verb = "atualizado"
        elif _confirm_delete(args, f"o ticket {current.title} ({current.id})"):
            ticket, verb = delete_ticket(container.tickets, args.item_id), "removido"
        else:
            print("Remoção cancelada.")
            return
    if args.json:
        _dump(ticket.model_dump(mode="json"))
        return
    print(f"Ticket {verb}:")
    _print_ticket(ticket)


def _list_prompts(container: Container, args: argparse.Namespace) -> None:
    """Lista as versões de prompt (ou mostra os detalhes de uma com ``--id``)."""
    if args.id:
        detail = get_prompt(container.prompts, args.id)
        if args.json:
            _dump(detail.model_dump(mode="json"))
        else:
            print(render_prompt_detail(detail, is_default=detail.is_default))
        return
    versions = list_prompt_versions(container.prompts)
    if args.json:
        _dump([v.model_dump(mode="json") for v in versions])
        return
    default = next((v.version for v in versions if v.is_default), None)
    print(render_versions(versions, default, details=args.details))


def _parse_prompt_changes(args: argparse.Namespace) -> list[PromptChange] | None:
    """Lê ``--changes`` ou ``--what/--why/--expected-effect``. Devolve ``None`` se nada foi informado."""
    single_parts = (args.what, args.why, args.expected_effect)
    if args.changes is not None and any(part is not None for part in single_parts):
        raise ValidationFailed("Use --changes OU --what/--why/--expected-effect, não os dois.")
    if args.changes is not None:
        raw_text = args.changes
        candidate = Path(raw_text)
        if candidate.is_file():
            raw_text = candidate.read_text(encoding="utf-8")
        try:
            data = json.loads(raw_text)
        except ValueError:
            raise ValidationFailed("JSON inválido em --changes.") from None
        if not isinstance(data, list):
            raise ValidationFailed("--changes deve ser uma lista JSON de mudanças.")
        changes: list[PromptChange] = []
        for item in data:
            if not isinstance(item, dict) or not {"what", "why", "expected_effect"} <= set(item):
                raise ValidationFailed("Cada mudança em --changes deve ter what, why e expected_effect.")
            changes.append(
                PromptChange.model_construct(
                    what=str(item["what"]), why=str(item["why"]), expected_effect=str(item["expected_effect"])
                )
            )
        return changes
    if any(part is not None for part in single_parts):
        if not all(part is not None for part in single_parts):
            raise ValidationFailed("Para registrar uma mudança, informe --what, --why e --expected-effect juntos.")
        return [PromptChange.model_construct(what=args.what, why=args.why, expected_effect=args.expected_effect)]
    return None


def _split_kv(spec: str, flag: str) -> tuple[str, str]:
    """Separa ``NOME=VALOR`` de uma flag da CLI."""
    if "=" not in spec:
        raise ValidationFailed(f"Formato inválido em {flag} {spec!r}: use NOME=VALOR.")
    name, value = spec.split("=", 1)
    return name.strip(), value


def _apply_prompt_file_args(base_files: dict[str, str], args: argparse.Namespace) -> dict[str, str]:
    """Aplica ``--files-dir``, ``--file``, ``--set`` e ``--remove-file`` sobre o mapa base de arquivos."""
    files = dict(base_files)
    if args.files_dir is not None:
        if not args.files_dir.is_dir():
            raise ValidationFailed(f"Pasta não encontrada em --files-dir: {args.files_dir}")
        for path in sorted(args.files_dir.iterdir()):
            if path.is_file() and path.name != META_FILE:
                files[path.name] = path.read_bytes().decode("utf-8")
    for spec in args.file_maps:
        name, path_str = _split_kv(spec, "--file")
        path = Path(path_str)
        if not path.is_file():
            raise ValidationFailed(f"Arquivo não encontrado para --file {name}: {path}")
        files[name] = path.read_bytes().decode("utf-8")
    for spec in args.inline_files:
        name, content = _split_kv(spec, "--set")
        files[name] = content
    for name in args.remove_files:
        files.pop(name.strip(), None)
    return files


def _cmd_prompt(container: Container, args: argparse.Namespace) -> None:
    """``prompt list|create|delete`` usando ``services/prompts`` (versões são imutáveis)."""
    if args.action == "list":
        _list_prompts(container, args)
        return

    if args.action == "create":
        base = get_prompt(container.prompts, args.based_on)
        parsed_changes = _parse_prompt_changes(args)
        files = _apply_prompt_file_args(base.files, args)
        detail = create_prompt(
            container.prompt_store,
            container.prompts,
            based_on=args.based_on,
            description=args.description,
            changes=parsed_changes if parsed_changes is not None else [],
            files=files,
            timezone=container.settings.app_timezone,
        )
        if args.json:
            _dump(detail.model_dump(mode="json"))
            return
        print("Prompt criado:")
        print(render_prompt_detail(detail, is_default=detail.is_default))
        return

    if args.version_id == BASE_PROMPT_VERSION:
        raise ValidationFailed(f"A versão base {BASE_PROMPT_VERSION} não pode ser removida.")
    current = get_prompt(container.prompts, args.version_id)
    if not _confirm_delete(args, f"a versão de prompt {current.version}"):
        print("Remoção cancelada.")
        return
    removed = delete_prompt(container.prompt_store, container.prompts, args.version_id)
    if args.json:
        _dump(removed.model_dump(mode="json"))
    else:
        print(f"Prompt removido: {removed.version} (base: {removed.based_on or '-'})")


# --- geração e histórico ---------------------------------------------------------------------------------------


def _cmd_generate(container: Container, args: argparse.Namespace) -> None:
    """Gera o conteúdo pedido diretamente via ``services/generators`` e imprime a saída legível (ou JSON).

    No modo ``all``: só falha se **todos** os tipos falharem; se só parte falhar, mostra o que deu certo e avisa os
    tipos com erro (``batch.warning``).
    """
    use_cache = not args.no_cache
    if args.content_type == ALL_OPTION_VALUE:
        batch = generate_all(
            container.generation,
            profile_id=args.customer,
            ticket_id=args.ticket,
            prompt_version=args.version,
            use_cache=use_cache,
            confirm_replace=args.confirm_replace,
        )
        batch.raise_if_all_failed()
        if args.json:
            _dump(batch.to_payload().model_dump(mode="json"))
            return
        done = [
            StoredRun(record=item.result.record, saved_path=item.result.saved_path)
            for item in batch.items
            if item.ok and item.result is not None
        ]
        print(render_run_header(done[0].record))
        for stored in done:
            print(f"\n{'=' * TEXT_WIDTH}\n{stored.record.content_type.label.upper()}\n{'=' * TEXT_WIDTH}")
            print(render_output(stored.record))
            print(f"\nJSON salvo em: {stored.saved_path}")
        if batch.warning:
            print(f"aviso: {batch.warning}", file=sys.stderr)
        return

    result = generate(
        container.generation,
        content_type=ContentType(args.content_type),
        profile_id=args.customer,
        ticket_id=args.ticket,
        prompt_version=args.version,
        use_cache=use_cache,
        confirm_replace=args.confirm_replace,
    )
    stored = StoredRun(record=result.record, saved_path=result.saved_path)
    if args.json:
        _dump(_run_payload(stored))
        return
    print(render_stored_run(stored))


def _page_params(args: argparse.Namespace) -> tuple[int, int]:
    """Página e itens por página, validados contra ``PAGE_SIZES``; devolve ``(limit, offset)``."""
    limit = DEFAULT_HISTORY_LIMIT if args.limit is None else args.limit
    if limit not in PAGE_SIZES:
        raise ValidationFailed(f"Itens por página: use {', '.join(map(str, PAGE_SIZES))}.")
    if args.page < 1:
        raise ValidationFailed("A página deve ser 1 ou maior.")
    return limit, (args.page - 1) * limit


def _check_page_exists(args: argparse.Namespace, page: Page) -> None:
    """Recusa uma página além da última; sem itens, só a página 1 existe."""
    if args.page > page.pages:
        raise ValidationFailed(f"A página {args.page} não existe: há {page.pages}.")


def _list_generations(container: Container, args: argparse.Namespace) -> None:
    """Lista uma página das execuções (``services/history``) em tabela (ou JSON)."""
    limit, offset = _page_params(args)
    filters = HistoryFilters(
        customer_id=args.customer,
        ticket_id=args.ticket,
        content_type=ContentType(args.content_type) if args.content_type else None,
        prompt_version=args.version,
        status=args.status,
        cache_key=args.cache_key,
    )
    page = list_runs(container.runs, filters, limit, offset)
    _check_page_exists(args, page)
    items = [summarize_run(stored).model_dump(mode="json") for stored in page.items]
    if args.json:
        _dump({"total": page.total, "items": items})
        return
    print(render_history_table(items))
    print(f"\n{render_page_info(args.page, limit, page.total, 'execução', 'execuções')}")


def _cmd_history(container: Container, args: argparse.Namespace) -> None:
    """``history generation`` ou ``history comparison [list|show <id>]``."""
    if args.history_command == "generation":
        _list_generations(container, args)
        return
    _cmd_comparison(container, args)


def _cmd_show(container: Container, args: argparse.Namespace) -> None:
    """Mostra uma execução salva com o mesmo renderizador do ``generate``."""
    stored = get_run(container.runs, args.run_id)
    if args.json:
        _dump(_run_payload(stored))
    else:
        print(render_stored_run(stored))


# --- comparação -------------------------------------------------------------------------------------------------


def _choose_saved(args: argparse.Namespace, saved: StoredComparison) -> bool:
    """Já existe comparação destas execuções: ``True`` carrega a salva, ``False`` faz outra do zero."""
    if args.load or args.new:
        return args.load
    if args.json:
        raise ValidationFailed("Já existe uma comparação destas execuções: informe --load ou --new.")
    print(f"Já existe uma comparação destas execuções ({saved.record.comparison_id}).")
    while True:
        answer = _ask("[c]arregar a comparação ou fazer uma [n]ova? ", "informe --load ou --new.").lower()
        if answer in LOAD_ANSWERS or answer in NEW_ANSWERS:
            return answer in LOAD_ANSWERS
        print("Responda c (carregar) ou n (nova).")


def _read_evaluations(path: Path) -> dict:
    """Notas do arquivo ``--evaluations`` (``{run_id: {critério: {score, justification}}}``)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValidationFailed(f"Não foi possível ler {path}: {exc.strerror}.") from None
    except ValueError:
        raise ValidationFailed(f"{path} não é um JSON válido.") from None
    if not isinstance(data, dict):
        raise ValidationFailed(f"{path} deve ser um objeto {{run_id: notas}}.")
    return data


def _ask_score(label: str) -> int:
    """Pergunta uma nota inteira da escala, repetindo até receber uma válida."""
    while True:
        answer = _ask(f"Nota de {label} ({rubric.SCORE_MIN}-{rubric.SCORE_MAX}): ", "informe --evaluations ARQ.json.")
        if answer.isdigit() and rubric.is_valid_score(int(answer)):
            return int(answer)
        print(f"Informe um número inteiro de {rubric.SCORE_MIN} a {rubric.SCORE_MAX}.")


def _ask_justification(label: str) -> str:
    """Pergunta uma justificativa não vazia, repetindo até receber uma."""
    while True:
        answer = _ask(f"Justificativa de {label}: ", "informe --evaluations ARQ.json.")
        if answer:
            return answer
        print("A justificativa é obrigatória.")


def _ask_evaluations(runs: Sequence[RunRecord]) -> dict:
    """Avaliação do zero de cada execução, no terminal: mostra a saída e pergunta as notas."""
    evaluations: dict = {}
    for record in runs:
        print(f"\n{'=' * TEXT_WIDTH}\nVERSÃO {record.prompt_version}\n{'=' * TEXT_WIDTH}")
        print(render_version_header(record))
        print()
        print(render_output(record))
        print(f"\nAVALIAÇÃO DA {record.prompt_version}. {render_scale()}")
        scores = {}
        for criterion in rubric.CRITERIA:
            print(f"\n{criterion.label}: {criterion.description}")
            scores[criterion.key] = {
                "score": _ask_score(criterion.label), "justification": _ask_justification(criterion.label),
            }
        evaluations[record.run_id] = scores
    return evaluations


def _cmd_compare(container: Container, args: argparse.Namespace) -> None:
    """Compara execuções já feitas diretamente via ``services/comparison``: nada é gerado aqui."""
    stored_runs = load_comparable_runs(container.runs, args.run_ids)
    runs = [item.record for item in stored_runs]
    saved = find_saved_comparison(container.comparisons, args.run_ids)
    if saved is not None and _choose_saved(args, saved):
        if args.json:
            _dump(_comparison_payload(saved))
        else:
            print(render_comparison(saved))
        return
    if args.json and args.evaluations is None:
        raise ValidationFailed("Com --json, informe as notas em --evaluations ARQ.json.")

    if not args.json:
        print(render_scenario_header(runs[0]))
        chosen = {record.prompt_version for record in runs}
        versions = [v for v in container.prompts.versions() if v.version in chosen]
        changes = render_version_changes(versions)
        if changes:
            print(f"\n{changes}")
    conclusion = args.conclusion
    if args.evaluations is not None:
        evaluations = _read_evaluations(args.evaluations)
    else:
        evaluations = _ask_evaluations(runs)
        if conclusion is None:
            conclusion = _ask("\nConclusão (opcional; Enter para pular): ", "informe --conclusion.")
    stored = save_comparison(
        container.comparison, run_ids=args.run_ids, evaluations=evaluations, conclusion=conclusion or None
    )
    if args.json:
        _dump(_comparison_payload(stored))
    else:
        print(f"\nComparação salva.\n\n{render_comparison(stored)}")


def _list_comparisons(container: Container, args: argparse.Namespace) -> None:
    """Lista uma página das comparações salvas em tabela (ou JSON)."""
    limit, offset = _page_params(args)
    page = list_comparisons(container.comparisons, limit, offset)
    _check_page_exists(args, page)
    items = [summarize_comparison(item).model_dump(mode="json") for item in page.items]
    if args.json:
        _dump({"total": page.total, "items": items})
        return
    print(render_comparisons_table(items))
    print(f"\n{render_page_info(args.page, limit, page.total, 'comparação', 'comparações')}")


def _cmd_comparison(container: Container, args: argparse.Namespace) -> None:
    """``history comparison [list|show <id>]``: lista as comparações salvas ou mostra uma pelo id."""
    if args.comparison_command in (None, "list"):
        _list_comparisons(container, args)
        return
    stored = get_comparison(container.comparisons, args.comparison_id)
    if args.json:
        _dump(_comparison_payload(stored))
    else:
        print(render_comparison(stored))


# Subcomando -> função que o executa.
_COMMANDS: dict[str, Callable[[Container, argparse.Namespace], None]] = {
    "meta": _cmd_meta,
    "customer": _cmd_customer,
    "ticket": _cmd_ticket,
    "prompt": _cmd_prompt,
    "generate": _cmd_generate,
    "history": _cmd_history,
    "show": _cmd_show,
    "compare": _cmd_compare,
}


def main(argv: Sequence[str] | None = None, container: Container | None = None) -> int:
    """Ponto de entrada. Devolve o código de saída em vez de chamar ``sys.exit`` (facilita os testes).

    ``container`` permite injetar dependências nos testes; sem ele, monta o ``Container`` padrão do processo.
    """
    args = build_parser().parse_args(argv)
    try:
        effective = container or build_container()
        _COMMANDS[args.command](effective, args)
        return EXIT_OK
    except DomainError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        if isinstance(exc, CacheReplaceRequired):
            print(f"Repita o comando com {CONFIRM_REPLACE_FLAG} para substituir e gerar.", file=sys.stderr)
        return next((code for cls, code in ERROR_EXIT_CODES.items() if isinstance(exc, cls)), EXIT_USAGE)


if __name__ == "__main__":
    raise SystemExit(main())
