/** Bloco numerado da tela (título, dica curta e conteúdo). */
export default function Section({ step, title, hint, children }) {
  return (
    <section className="panel" aria-labelledby={`sec-${step}`}>
      <header className="panel-header">
        <span className="step" aria-hidden="true">
          {step}
        </span>
        <div>
          <h2 id={`sec-${step}`}>{title}</h2>
          {hint && <p className="hint">{hint}</p>}
        </div>
      </header>
      {children}
    </section>
  );
}
