import CatalogCrud from "../components/CatalogCrud.jsx";
import TextField from "../components/TextField.jsx";
import { createTicket, deleteTicket, updateTicket } from "../api/client.js";
import { useCrudActions } from "../hooks/useCrudActions.js";

const EMPTY_DRAFT = { id: null, title: "", text: "" };

const API = {
  create: createTicket,
  update: updateTicket,
  remove: deleteTicket,
  created: "Ticket adicionado.",
  updated: "Ticket atualizado.",
  removed: "Ticket removido.",
};

const TEXTS = {
  listTitle: "Tickets",
  listHint: "Os tickets que aparecem na aba Gerar.",
  empty: "Nenhum ticket. Adicione o primeiro ao lado.",
  addTitle: "Novo ticket",
  editTitle: "Editar ticket",
  addButton: "Adicionar ticket",
  editButton: "Editar ticket",
};

/** Aba Ticket: CRUD dos tickets, gravados em `catalog/tickets.json` (ADR 0037). */
export default function TicketsPage({ catalog }) {
  const { meta, tickets, refreshTickets } = catalog;
  const actions = useCrudActions(API, refreshTickets);

  return (
    <CatalogCrud
      id="tickets"
      texts={TEXTS}
      items={tickets}
      itemLabel={(ticket) => ticket.title}
      renderItem={(ticket) => (
        <>
          <strong>{ticket.title}</strong>
          <p className="hint crud-excerpt">{ticket.text}</p>
        </>
      )}
      emptyDraft={EMPTY_DRAFT}
      toDraft={({ id, title, text }) => ({ id, title, text })}
      isValid={(draft) => draft.title.trim() !== "" && draft.text.trim() !== ""}
      renderFields={(draft, setDraft) => (
        <>
          <TextField
            label="Título"
            value={draft.title}
            onChange={(title) => setDraft({ ...draft, title })}
            maxLength={meta.limits.max_ticket_title_chars}
            placeholder="Resuma o problema em uma linha"
          />
          <TextField
            label="Corpo"
            multiline
            value={draft.text}
            onChange={(text) => setDraft({ ...draft, text })}
            maxLength={meta.limits.max_ticket_chars}
            placeholder="Descreva o problema relatado pelo cliente..."
          />
        </>
      )}
      actions={actions}
    />
  );
}
