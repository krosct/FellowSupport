import SegmentedControl from "./SegmentedControl.jsx";
import { scoreCaption, scoreOptions } from "../lib/rubric.js";

/**
 * Formulário da rubrica: para cada critério, a nota (botões de 1 a 5) e uma justificativa curta. Reutilizável (Comparar
 * mostra um por versão). Critérios, escala e limite da justificativa vêm de `rubric` (/api/meta); `value` é
 * `{ [critério]: { score, justification } }`. `onChange` recebe uma função `(atual) => novo`, e não o objeto pronto:
 * duas edições no mesmo ciclo de eventos (nota e justificativa em sequência rápida) partem do estado mais recente do
 * pai, em vez do `value` capturado neste render, e nenhuma se perde.
 */
export default function RubricForm({ rubric, value, onChange, idPrefix, disabled = false }) {
  const options = scoreOptions(rubric);
  const update = (key, patch) => onChange((current) => ({ ...current, [key]: { ...current[key], ...patch } }));

  return (
    <div className="rubric-form">
      {rubric.criteria.map((criterion) => {
        const item = value[criterion.key];
        const inputId = `${idPrefix}-${criterion.key}`;
        return (
          <fieldset key={criterion.key} className="rubric-criterion" disabled={disabled}>
            <legend>{criterion.label}</legend>
            <p className="hint">{criterion.description}</p>
            <div className="rubric-score">
              <SegmentedControl
                label={`Nota de ${criterion.label}`}
                options={options}
                value={item.score}
                onChange={(score) => update(criterion.key, { score })}
              />
              <strong className="rubric-score-caption" aria-live="polite">
                {scoreCaption(rubric, item.score)}
              </strong>
            </div>
            <label htmlFor={inputId} className="sr-only">
              Justificativa de {criterion.label}
            </label>
            <input
              id={inputId}
              type="text"
              placeholder="Justificativa curta"
              maxLength={rubric.justification_max_chars}
              value={item.justification}
              onChange={(event) => update(criterion.key, { justification: event.target.value })}
            />
          </fieldset>
        );
      })}
    </div>
  );
}
