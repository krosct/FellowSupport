"""Apoio compartilhado pelos testes: clientes de LLM roteirizados (porta ``LLMClient``), execução direta da CLI
sobre o ``Container`` (ADR 0041) e um atalho para gerar uma execução por versão."""

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.adapters.storage.json_files import JsonTicketRepo
from app.adapters.storage.prompt_files import FilePromptStore
from app.config import BASE_DIR
from app.domain.llm_output import extract_json_object
from app.domain.models import ContentType, Ticket
from app.domain.prompting.registry import PromptChange, PromptRegistry
from app.ports.llm import ChatMessage, LLMParams, LLMResult
from app.services.prompts import create_prompt

# A versão padrão é a mais nova (ADR 0039): os testes que não pedem versão a leem daqui e não quebram na v4.
LATEST_VERSION = PromptRegistry(FilePromptStore(BASE_DIR / "prompts")).latest().version


class LLMRoteirizado:
    """LLM de teste: devolve (ou levanta) as respostas na ordem e guarda as mensagens recebidas."""

    def __init__(self, *respostas: str | Exception | LLMResult) -> None:
        self._respostas = list(respostas)
        self.chamadas: list[list[ChatMessage]] = []

    def complete(self, messages: Sequence[ChatMessage], schema: type[BaseModel], params: LLMParams) -> LLMResult:
        # Registra as mensagens recebidas e devolve ou lança o próximo item roteirizado (um ``LLMResult`` pronto
        # passa direto, para simular razão de parada e provedor).
        self.chamadas.append([dict(m) for m in messages])  # type: ignore[misc]
        item = self._respostas.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, LLMResult):
            return item
        return LLMResult(
            text=item, parsed=extract_json_object(item), usage={"prompt_tokens": 10, "completion_tokens": 5},
            latency_ms=1, model_used="vendor/efetivo",
        )


class LLMPorSchema:
    """LLM de teste seguro para threads: a resposta depende do schema pedido (não da ordem das chamadas).

    ``respostas`` mapeia o schema para um texto ou uma exceção; schema ausente cai no ``FakeLLM``. Útil no modo
    ``all``, em que as quatro chamadas chegam em ordem imprevisível.
    """

    def __init__(self, respostas: dict[type[BaseModel], str | Exception]) -> None:
        import threading

        from app.adapters.llm.fake import FakeLLM

        self._respostas = respostas
        self._fake = FakeLLM()
        self._lock = threading.Lock()
        self.chamadas: list[type[BaseModel]] = []
        self.threads: set[int] = set()

    def complete(self, messages: Sequence[ChatMessage], schema: type[BaseModel], params: LLMParams) -> LLMResult:
        import threading

        # Registra chamada e thread com lock e usa FakeLLM se o schema não foi sobrescrito.
        with self._lock:
            self.chamadas.append(schema)
            self.threads.add(threading.get_ident())
        item = self._respostas.get(schema)
        if item is None:
            return self._fake.complete(messages, schema, params)
        if isinstance(item, Exception):
            raise item
        usage = {"prompt_tokens": 1, "completion_tokens": 1}
        return LLMResult(text=item, parsed=extract_json_object(item), usage=usage, latency_ms=1,
                         model_used="vendor/efetivo")


class FakeContador:
    """``FakeLLM`` que conta as chamadas (seguro para threads): prova que o acerto de cache não chama o LLM."""

    def __init__(self) -> None:
        import threading

        from app.adapters.llm.fake import FakeLLM

        self._fake = FakeLLM()
        self._lock = threading.Lock()
        self.chamadas = 0

    def complete(self, messages: Sequence[ChatMessage], schema: type[BaseModel], params: LLMParams) -> LLMResult:
        # Incrementa o contador com lock e delega a resposta ao FakeLLM.
        with self._lock:
            self.chamadas += 1
        return self._fake.complete(messages, schema, params)


def gerar_versoes(
    container: Any,
    versoes: Sequence[str] = ("v1", "v2"),
    *,
    tipo: ContentType = ContentType.RESOLUTION_STEPS,
    perfil: str = "marta",
    ticket: str = "t-2fa",
    nova: bool = False,
) -> list[str]:
    """Gera o cenário em cada versão (como a aba Gerar) e devolve os ``run_id`` na ordem das versões.

    ``nova=True`` não consulta o cache (e confirma a troca da entrada): gera execuções novas, não acertos de cache.
    """
    from app.services.generators import generate

    seed_prompt_versions(container.settings.prompts_dir, *versoes)
    return [
        generate(
            container.generation, content_type=tipo, profile_id=perfil, ticket_id=ticket, prompt_version=versao,
            use_cache=not nova, confirm_replace=nova,
        ).record.run_id
        for versao in versoes
    ]


def seed_prompt_versions(prompts_dir: Path, *versions: str) -> None:
    """Cria versões derivadas válidas em ``prompts_dir`` (em ``tmp_path``) quando um teste precisa de v2/v3."""
    store = FilePromptStore(prompts_dir)
    registry = PromptRegistry(store)
    existing = {v.version for v in registry.versions()}
    for version in versions:
        if version in existing:
            continue
        base = sorted(existing)[-1]
        detail = registry.detail(base)
        files = {**detail.files, "system.md": f"{detail.files['system.md']}\n<!-- {version} -->"}
        create_prompt(
            store,
            registry,
            based_on=base,
            description=f"Versão sintética {version}",
            changes=[
                PromptChange(
                    what=f"Ajuste {version}",
                    why=f"Isolamento de teste ({version})",
                    expected_effect="Comparação determinística",
                )
            ],
            files=files,
            timezone="America/Sao_Paulo",
        )
        existing.add(version)


def seed_ticket(
    catalog_dir: Path, ticket_id: str, title: str = "Ticket de teste", text: str = "Relato de teste."
) -> None:
    """Acrescenta um ticket sintético ao catálogo em ``tmp_path`` se ainda não existir."""
    repo = JsonTicketRepo(catalog_dir)
    if all(item.id != ticket_id for item in repo.list_all()):
        repo.add(Ticket(id=ticket_id, title=title, text=text))


def cli(argv: Sequence[str], container: Any) -> int:
    """Roda a CLI diretamente contra o ``Container`` (mesmo nível da API, sem HTTP)."""
    from app.adapters.cli.main import main

    return main(list(argv), container)
