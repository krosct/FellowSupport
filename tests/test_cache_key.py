"""Testes da chave de cache (ADR 0010 e 0028): muda com qualquer insumo relevante e ignora ruído de formatação."""

import hashlib
import json
import re
from dataclasses import dataclass, replace

import pytest

from app.domain.cache_key import compute_cache_key, normalize_ticket
from app.domain.models import CACHE_KEY_PATTERN, Channel, CommStyle, ContentType, CustomerProfile, TechLevel

PERFIL = CustomerProfile(
    id="marta", name="Dona Marta", tech_level=TechLevel.LEIGO, comm_style=CommStyle.DIDATICO, channel=Channel.TELEFONE
)


@dataclass(frozen=True)
class Entrada:
    """Os insumos da chave, com valores-base; cada teste troca um campo e compara a chave."""

    profile: CustomerProfile = PERFIL
    ticket_text: str = "O SMS não chega."
    content_type: ContentType = ContentType.DIAGNOSIS
    prompt_version: str = "v1"
    prompt_sha256: str = "a" * 64
    provider: str = "openrouter"
    model: str = "vendor/modelo:free"
    temperature: float = 0.2
    max_tokens: int = 8000
    structured_mode: str = "json_schema"
    reasoning: str = "default"

    def chave(self) -> str:
        # Calcula a chave SHA-256 usando todos os campos desta instância.
        return compute_cache_key(**self.__dict__)


BASE = Entrada()


def test_chave_e_sha256_hexadecimal_deterministica() -> None:
    chave = BASE.chave()
    assert re.fullmatch(CACHE_KEY_PATTERN, chave)
    assert chave == Entrada().chave()


def test_chave_e_o_sha256_do_json_canonico() -> None:
    """Fixa a forma canônica (chaves ordenadas, sem espaços): mudar o formato quebra caches antigos de propósito."""
    payload = {
        "profile": PERFIL.model_dump(mode="json"), "ticket": "O SMS não chega.", "content_type": "diagnosis",
        "prompt_version": "v1", "prompt_sha256": "a" * 64, "provider": "openrouter",
        "model": "vendor/modelo:free", "temperature": 0.2, "max_tokens": 8000,
        "structured_mode": "json_schema", "reasoning": "default",
    }
    esperado = json.dumps(dict(reversed(list(payload.items()))), sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False)
    assert BASE.chave() == hashlib.sha256(esperado.encode("utf-8")).hexdigest()


# Um caso por campo: todos precisam mudar a chave (ADR 0010).
ALTERACOES = {
    "conteúdo do perfil (nível)": {"profile": PERFIL.model_copy(update={"tech_level": TechLevel.AVANCADO})},
    "conteúdo do perfil (estilo)": {"profile": PERFIL.model_copy(update={"comm_style": CommStyle.DIRETO})},
    "conteúdo do perfil (canal)": {"profile": PERFIL.model_copy(update={"channel": Channel.CHAT})},
    "conteúdo do perfil (nome)": {"profile": PERFIL.model_copy(update={"name": "Marta"})},
    "id do perfil": {"profile": PERFIL.model_copy(update={"id": "outra"})},
    "ticket": {"ticket_text": "O SMS chega atrasado."},
    "tipo de conteúdo": {"content_type": ContentType.FLOW_SUMMARY},
    "versão do prompt": {"prompt_version": "v2"},
    "hash do prompt": {"prompt_sha256": "b" * 64},
    "provedor": {"provider": "fake"},
    "modelo": {"model": "outro/modelo:free"},
    "temperatura": {"temperature": 0.3},
    "max_tokens": {"max_tokens": 4000},
    "modo estruturado": {"structured_mode": "json_object"},
    "raciocínio": {"reasoning": "off"},
}


@pytest.mark.parametrize("campo", list(ALTERACOES))
def test_chave_muda_quando_muda_qualquer_insumo(campo: str) -> None:
    assert replace(BASE, **ALTERACOES[campo]).chave() != BASE.chave()


def test_todas_as_alteracoes_geram_chaves_distintas_entre_si() -> None:
    chaves = {replace(BASE, **mudanca).chave() for mudanca in ALTERACOES.values()}
    assert len(chaves) == len(ALTERACOES)


@pytest.mark.parametrize(
    "texto",
    ["  O SMS não chega.  ", "O  SMS   não\tchega.", "O SMS\nnão chega.\n", "\n\nO SMS não chega."],
)
def test_diferenca_so_de_espacos_no_ticket_nao_muda_a_chave(texto: str) -> None:
    assert replace(BASE, ticket_text=texto).chave() == BASE.chave()


def test_ordem_das_chaves_do_perfil_nao_muda_a_chave() -> None:
    embaralhado = CustomerProfile.model_validate(
        {"channel": "telefone", "comm_style": "didático", "tech_level": "leigo", "name": "Dona Marta", "id": "marta"}
    )
    assert replace(BASE, profile=embaralhado).chave() == BASE.chave()


def test_normalize_ticket_colapsa_e_apara() -> None:
    assert normalize_ticket("  a \t b\n\nc  ") == "a b c"
    assert normalize_ticket("") == ""
