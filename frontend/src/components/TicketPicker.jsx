import OptionCard from "./OptionCard.jsx";
import SegmentedControl from "./SegmentedControl.jsx";

// Modos de entrada do ticket (rótulos de interface, não do domínio).
const MODES = [
  { value: "sample", label: "Ticket de exemplo" },
  { value: "free", label: "Digitar ticket" },
];

/**
 * Seletor de ticket: escolhe um exemplo do catálogo (mostrando título e texto) ou digita um texto livre.
 * O limite de caracteres vem de /api/meta (`maxChars`). A geração a partir do texto livre chega na Etapa 1.
 */
export default function TicketPicker({ tickets, mode, onModeChange, ticketId, onTicketChange, freeText, onFreeTextChange, maxChars }) {
  const selected = tickets.find((ticket) => ticket.id === ticketId);

  return (
    <div className="stack">
      <SegmentedControl label="Origem do ticket" options={MODES} value={mode} onChange={onModeChange} />

      {mode === "sample" ? (
        <>
          <div className="option-list" role="radiogroup" aria-label="Ticket de exemplo">
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
        </>
      ) : (
        <label className="free-ticket">
          <span className="sr-only">Texto do ticket</span>
          <textarea
            rows={8}
            maxLength={maxChars}
            placeholder="Descreva o problema relatado pelo cliente..."
            value={freeText}
            onChange={(event) => onFreeTextChange(event.target.value)}
          />
          <small className="counter">
            {freeText.length} / {maxChars}
          </small>
        </label>
      )}
    </div>
  );
}
