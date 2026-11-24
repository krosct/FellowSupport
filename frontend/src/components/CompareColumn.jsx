import RunInfo from "./RunInfo.jsx";
import OutputView from "./OutputView.jsx";
import RubricForm from "./RubricForm.jsx";

/**
 * Um lado da comparação: cabeçalho da versão, dados da execução, a saída e o formulário da rubrica do candidato.
 * Reaproveita `RunInfo`, `OutputView` e `RubricForm`. Os estados (notas) ficam no `ComparePage`; aqui só se desenha.
 */
export default function CompareColumn({ item, meta, form, onFormChange }) {
  const { run } = item;
  return (
    <article className="compare-col" aria-label={`Versão ${item.prompt_version}`}>
      <h3>Prompt {item.prompt_version}</h3>
      <RunInfo run={run} savedPath={item.saved_path} contentTypes={meta.content_types} />
      <OutputView run={run} confidenceLevels={meta.confidence_levels} />
      <section className="stack" aria-label={`Rubrica da ${item.prompt_version}`}>
        <h4>Sua avaliação</h4>
        <RubricForm rubric={meta.rubric} value={form} onChange={onFormChange} idPrefix={`rubric-${run.run_id}`} />
      </section>
    </article>
  );
}
