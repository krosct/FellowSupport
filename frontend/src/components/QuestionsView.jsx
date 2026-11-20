import Badge from "./Badge.jsx";

/**
 * Perguntas de esclarecimento priorizadas, cada uma com o motivo e o que a resposta destrava, e o veredito
 * "dá para avançar sem as respostas". Reutilizável (Comparar e Histórico).
 */
export default function QuestionsView({ questions }) {
  const canProceed = questions.can_proceed_without_answers;
  return (
    <div className="questions-view">
      <ol className="question-list">
        {questions.questions.map((item) => (
          <li key={item.priority} className="question-card">
            <header className="question-head">
              <Badge kind={item.priority === 1 ? "low" : "neutral"}>Prioridade {item.priority}</Badge>
            </header>
            <p className="question-text">{item.question}</p>
            <dl className="step-notes">
              <div>
                <dt>Motivo</dt>
                <dd>{item.why_it_matters}</dd>
              </div>
              <div>
                <dt>Destrava</dt>
                <dd>{item.unlocks}</dd>
              </div>
            </dl>
          </li>
        ))}
      </ol>

      <section className="callout" data-kind={canProceed ? "ok" : "warn"}>
        <h3>Dá para avançar sem as respostas?</h3>
        <div className="conclusion-head">
          <Badge kind={canProceed ? "ok" : "warn"}>{canProceed ? "Sim" : "Não"}</Badge>
        </div>
        <p>{questions.proceed_note}</p>
      </section>
    </div>
  );
}
