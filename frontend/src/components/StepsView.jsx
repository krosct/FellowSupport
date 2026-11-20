import Badge from "./Badge.jsx";

/**
 * Passo a passo de resolução: abertura, passos numerados (cada um com resultado esperado e plano B),
 * quando escalar e fechamento. Reutilizável (Comparar e Histórico usarão o mesmo componente).
 */
export default function StepsView({ steps }) {
  return (
    <div className="steps-view">
      <p className="lead">{steps.opening}</p>

      <ol className="step-list">
        {steps.steps.map((step) => (
          <li key={step.order} className="step-card">
            <header className="step-card-head">
              <Badge kind="ok">{step.order}</Badge>
              <h4>{step.title}</h4>
            </header>
            <p>{step.instruction}</p>
            <dl className="step-notes">
              <div data-kind="expected">
                <dt>Resultado esperado</dt>
                <dd>{step.expected_result}</dd>
              </div>
              <div data-kind="fallback">
                <dt>Se falhar</dt>
                <dd>{step.if_it_fails}</dd>
              </div>
            </dl>
          </li>
        ))}
      </ol>

      <section className="callout" data-kind="warn">
        <h3>Quando escalar</h3>
        <p>{steps.when_to_escalate}</p>
      </section>

      <section className="callout">
        <h3>Fechamento</h3>
        <p>{steps.closing}</p>
      </section>
    </div>
  );
}
