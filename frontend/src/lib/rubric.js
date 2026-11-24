// Funções puras sobre a rubrica (`meta.rubric`, servida por /api/meta). Nenhum critério, rótulo ou escala é repetido
// aqui: tudo é lido da rubrica recebida.

/** Avaliação em branco: um item `{ score: null, justification: "" }` por critério. */
export const emptyEvaluation = (rubric) =>
  Object.fromEntries(rubric.criteria.map((criterion) => [criterion.key, { score: null, justification: "" }]));

/** `true` quando todos os critérios têm nota e justificativa (não vazia). */
export const isEvaluationComplete = (rubric, value) =>
  rubric.criteria.every((criterion) => {
    const item = value?.[criterion.key];
    return item?.score != null && item.justification.trim() !== "";
  });

/** Corpo enviado à API: notas inteiras e justificativas aparadas, um item por critério. */
export const evaluationPayload = (rubric, value) =>
  Object.fromEntries(
    rubric.criteria.map((criterion) => [
      criterion.key,
      { score: value[criterion.key].score, justification: value[criterion.key].justification.trim() },
    ]),
  );

/** Soma das notas de uma avaliação gravada. */
export const totalOf = (rubric, evaluation) =>
  rubric.criteria.reduce((sum, criterion) => sum + evaluation[criterion.key].score, 0);

/** Notas possíveis da escala, de `min` a `max`. */
export const scoreOptions = (rubric) =>
  Array.from({ length: rubric.scale.max - rubric.scale.min + 1 }, (_, index) => {
    const score = rubric.scale.min + index;
    return { value: score, label: String(score) };
  });

/** Texto exibido sob a nota: o rótulo da escala com a primeira letra maiúscula, ou "Sem nota" enquanto não há nota. */
export const scoreCaption = (rubric, score) => {
  if (score == null) return "Sem nota";
  const label = rubric.scale.labels[score];
  return label.charAt(0).toUpperCase() + label.slice(1);
};
