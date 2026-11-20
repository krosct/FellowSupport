"""Testes da v2 dos prompts: derivação da v1, mudanças justificadas, regras de adaptação e tamanho controlado."""

from __future__ import annotations

import json

import pytest

from app.adapters.storage.json_files import JsonProfileRepo, JsonTicketRepo
from app.adapters.storage.prompt_files import FilePromptStore
from app.config import BASE_DIR
from app.domain.models import ContentType
from app.domain.prompting.engine import ADAPTATION_DIMENSIONS, ADAPTATION_FILE, PromptBuilder
from app.domain.prompting.registry import PromptRegistry

PROMPTS = BASE_DIR / "prompts"
CATALOG = BASE_DIR / "catalog"

# Quanto a v2 pode crescer em relação à v1 (o PDF pede para evitar prompts gigantes): teto de 2x por arquivo de tipo.
MAX_GROWTH = 2.0


@pytest.fixture(scope="module")
def registry() -> PromptRegistry:
    return PromptRegistry(FilePromptStore(PROMPTS))


def _perfil(perfil_id: str):
    return JsonProfileRepo(CATALOG).get(perfil_id)


def test_v2_deriva_da_v1_e_toda_mudanca_e_justificada(registry: PromptRegistry) -> None:
    meta = registry.get("v2")
    assert meta.based_on == "v1" and meta.content_sha256 == registry.actual_sha256("v2")
    assert len(meta.changes) >= 4
    for mudanca in meta.changes:
        assert mudanca.what and mudanca.why and mudanca.expected_effect and mudanca.risk, mudanca.what


def test_v2_so_altera_o_que_o_meta_declara(registry: PromptRegistry) -> None:
    """system.md e repair.md ficam idênticos aos da v1: a comparação isola as mudanças de adaptação."""
    for nome in ("system.md", "repair.md"):
        assert registry.read("v2", nome) == registry.read("v1", nome)
    for nome in ("adaptation.json", "context.md", *(f"{t.value}.md" for t in ContentType)):
        assert registry.read("v2", nome) != registry.read("v1", nome)


def test_v2_tem_regra_explicita_para_cada_valor_de_cada_dimensao() -> None:
    adaptacao = json.loads((PROMPTS / "v2" / ADAPTATION_FILE).read_text(encoding="utf-8"))
    for dimensao, enum_cls in ADAPTATION_DIMENSIONS.items():
        for valor in enum_cls:
            regra = adaptacao[dimensao][valor.value]
            # Começa pelo próprio rótulo e acrescenta ao menos uma regra (diferente do rótulo cru da v1).
            assert regra.startswith(valor.value) and len(regra) > len(valor.value) + 20


@pytest.mark.parametrize(
    ("perfil", "trechos"),
    [
        ("marta", ("Sem jargão", "analogia", "Um conceito por frase", "didático", "números por extenso")),
        ("rafael", ("explicação breve", "detalhado", "Saudação")),
        ("bianca", ("comandos, códigos de erro e trechos de log", "direto", "Mensagens curtas")),
    ],
)
def test_regras_do_perfil_chegam_ao_prompt_de_cada_tipo(registry: PromptRegistry, perfil: str, trechos) -> None:
    builder = PromptBuilder(registry)
    for tipo in ContentType:
        usuario = builder.build("v2", tipo, _perfil(perfil), "Relato.")[1]["content"]
        for trecho in trechos:
            assert trecho in usuario, (tipo, trecho)


@pytest.mark.parametrize("tipo", list(ContentType))
def test_v2_inclui_o_formato_do_canal_e_a_autoverificacao_em_todos_os_tipos(
    registry: PromptRegistry, tipo: ContentType
) -> None:
    """Inclusive no diagnóstico, que na v1 não recebia a restrição do canal."""
    usuario = PromptBuilder(registry).build("v2", tipo, _perfil("marta"), "Relato.")[1]["content"]
    assert "sem markdown" in usuario
    assert "Autoverificação" in usuario and "não escreva a lista na resposta" in usuario


def test_v2_prioriza_perguntas_e_verifica_cada_passo(registry: PromptRegistry) -> None:
    builder = PromptBuilder(registry)
    perguntas = builder.build("v2", ContentType.CLARIFYING_QUESTIONS, _perfil("rafael"), "x")[1]["content"]
    assert "mais separa as hipóteses" in perguntas and "mais fácil de o cliente responder" in perguntas
    passos = builder.build("v2", ContentType.RESOLUTION_STEPS, _perfil("rafael"), "x")[1]["content"]
    assert "nunca apenas" in passos and "resultado esperado" in passos
    fluxo = builder.build("v2", ContentType.FLOW_SUMMARY, _perfil("rafael"), "x")[1]["content"]
    assert "Funcionou?" in fluxo


def test_v2_mantem_o_ticket_como_dado(registry: PromptRegistry) -> None:
    ticket = JsonTicketRepo(CATALOG).get("t-2fa")
    usuario = PromptBuilder(registry).build("v2", ContentType.DIAGNOSIS, _perfil("marta"), ticket.text)[1]["content"]
    assert f"<ticket>\n{ticket.text}\n</ticket>" in usuario and "não instrução" in usuario


@pytest.mark.parametrize("tipo", list(ContentType))
def test_tamanho_da_v2_e_controlado(registry: PromptRegistry, tipo: ContentType) -> None:
    arquivo = f"{tipo.value}.md"
    assert len(registry.read("v2", arquivo)) <= MAX_GROWTH * len(registry.read("v1", arquivo))
