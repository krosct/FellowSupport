"""Criação, edição e remoção de clientes e tickets do catálogo (ADR 0037), sobre as portas ``ProfileStore`` e
``TicketStore``.

Existe como serviço para a API (e, se vier a precisar, a CLI) aplicarem **as mesmas regras** de validação: textos sem
espaços nas pontas e não vazios, nome e título curtos, corpo do ticket dentro de ``max_ticket_chars``. O id de um item
novo é gerado aqui e nunca muda, porque as execuções do histórico e o cache apontam para ele.
"""

import uuid

from app.domain.errors import ValidationFailed
from app.domain.models import (
    PROFILE_ID_PREFIX,
    PROFILE_NAME_MAX_CHARS,
    TICKET_ID_PREFIX,
    TICKET_TITLE_MAX_CHARS,
    Channel,
    CommStyle,
    CustomerProfile,
    TechLevel,
    Ticket,
)
from app.ports.repositories import ProfileStore, TicketStore

_ID_HEX_CHARS = 8


def _new_id(prefix: str) -> str:
    """Id novo: o prefixo do tipo mais 8 hexadecimais aleatórios (colisão é recusada pelo armazenamento)."""
    return f"{prefix}{uuid.uuid4().hex[:_ID_HEX_CHARS]}"


def _required(value: str, label: str, max_chars: int) -> str:
    """Texto aparado; ``ValidationFailed`` se ficar vazio ou passar de ``max_chars``."""
    value = value.strip()
    if not value:
        raise ValidationFailed(f"Informe {label}.")
    if len(value) > max_chars:
        raise ValidationFailed(f"{label[0].upper()}{label[1:]} passa do limite de {max_chars} caracteres.")
    return value


# --- tickets ---------------------------------------------------------------------------------------


def _ticket(ticket_id: str, title: str, text: str, max_text_chars: int) -> Ticket:
    return Ticket(
        id=ticket_id,
        title=_required(title, "o título do ticket", TICKET_TITLE_MAX_CHARS),
        text=_required(text, "o corpo do ticket", max_text_chars),
    )


def create_ticket(store: TicketStore, title: str, text: str, max_text_chars: int) -> Ticket:
    """Valida e grava um ticket novo com id gerado (``t-`` mais 8 hexadecimais)."""
    return store.add(_ticket(_new_id(TICKET_ID_PREFIX), title, text, max_text_chars))


def update_ticket(store: TicketStore, ticket_id: str, title: str, text: str, max_text_chars: int) -> Ticket:
    """Valida e troca título e texto do ticket; ``NotFound`` se o id não existir."""
    store.get(ticket_id)  # falha cedo com 404, antes de validar o corpo
    return store.update(_ticket(ticket_id, title, text, max_text_chars))


def delete_ticket(store: TicketStore, ticket_id: str) -> Ticket:
    """Remove o ticket e o devolve. As execuções já salvas guardam uma cópia dele e não são afetadas."""
    return store.remove(ticket_id)


# --- clientes --------------------------------------------------------------------------------------


def _profile(
    profile_id: str, name: str, tech_level: TechLevel, comm_style: CommStyle, channel: Channel
) -> CustomerProfile:
    return CustomerProfile(
        id=profile_id,
        name=_required(name, "o nome do cliente", PROFILE_NAME_MAX_CHARS),
        tech_level=tech_level,
        comm_style=comm_style,
        channel=channel,
    )


def create_profile(
    store: ProfileStore, name: str, tech_level: TechLevel, comm_style: CommStyle, channel: Channel
) -> CustomerProfile:
    """Valida e grava um cliente novo com id gerado (``c-`` mais 8 hexadecimais)."""
    return store.add(_profile(_new_id(PROFILE_ID_PREFIX), name, tech_level, comm_style, channel))


def update_profile(
    store: ProfileStore, profile_id: str, name: str, tech_level: TechLevel, comm_style: CommStyle, channel: Channel
) -> CustomerProfile:
    """Valida e troca os dados do cliente; ``NotFound`` se o id não existir."""
    store.get(profile_id)
    return store.update(_profile(profile_id, name, tech_level, comm_style, channel))


def delete_profile(store: ProfileStore, profile_id: str) -> CustomerProfile:
    """Remove o cliente e o devolve. As execuções já salvas guardam uma cópia dele e não são afetadas."""
    return store.remove(profile_id)
