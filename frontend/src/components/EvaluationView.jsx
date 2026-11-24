import Badge from "./Badge.jsx";
import { totalOf } from "../lib/rubric.js";

/**
 * Avaliação já gravada, só leitura: nota e justificativa de cada critério e o total (Histórico e Comparação).
 */
export default function EvaluationView({ title, evaluation, rubric }) {
  return (
    <section className="callout evaluation-view">
      <h3>{title}</h3>
      <ul className="evaluation-list">
        {rubric.criteria.map((criterion) => (
          <li key={criterion.key}>
            <span className="summary-label">{criterion.label}</span>
            <Badge kind="ok">{evaluation[criterion.key].score}</Badge>
            <span className="evaluation-why">{evaluation[criterion.key].justification}</span>
          </li>
        ))}
      </ul>
      <p className="hint">Total {totalOf(rubric, evaluation)} de {rubric.total_max}</p>
    </section>
  );
}
