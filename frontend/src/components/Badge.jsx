/** Etiqueta curta. `kind` escolhe a cor (level, style, channel, neutral) por tokens em app.css. */
export default function Badge({ kind = "neutral", children }) {
  return (
    <span className="badge" data-kind={kind}>
      {children}
    </span>
  );
}
