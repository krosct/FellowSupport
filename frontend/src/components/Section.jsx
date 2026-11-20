/**
 * Bloco da tela (título, dica curta e conteúdo). `step` é opcional e mostra o número do passo; `id` identifica o
 * título para leitores de tela e precisa ser único na página (padrão: `sec-<step>`).
 */
export default function Section({ step, id, title, hint, children }) {
  const headingId = id ?? `sec-${step}`;
  return (
    <section className="panel" aria-labelledby={headingId}>
      <header className="panel-header">
        {step != null && (
          <span className="step" aria-hidden="true">
            {step}
          </span>
        )}
        <div>
          <h2 id={headingId}>{title}</h2>
          {hint && <p className="hint">{hint}</p>}
        </div>
      </header>
      {children}
    </section>
  );
}
