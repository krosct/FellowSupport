import OptionCard from "./OptionCard.jsx";

/**
 * Seletor de ticket da aba Gerar: escolhe um ticket do catálogo e mostra o texto completo dele. Criar, editar e remover
 * tickets é na aba Ticket.
 */
export default function TicketPicker({ tickets, ticketId, onTicketChange }) {
  const selected = tickets.find((ticket) => ticket.id === ticketId);

  if (tickets.length === 0) return <p className="hint">Nenhum ticket. Adicione um na aba Ticket.</p>;

  return (
    <div className="stack">
      <div className="option-list" role="radiogroup" aria-label="Ticket">
        {tickets.map((ticket) => (
          <OptionCard key={ticket.id} name="ticket" value={ticket.id} checked={ticketId === ticket.id} onChange={onTicketChange}>
            <strong>{ticket.title}</strong>
          </OptionCard>
        ))}
      </div>
      {selected && (
        <article className="ticket-text" aria-live="polite">
          <h3>{selected.title}</h3>
          <p>{selected.text}</p>
        </article>
      )}
    </div>
  );
}
