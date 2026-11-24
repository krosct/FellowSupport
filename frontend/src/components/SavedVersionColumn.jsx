import OutputView from "./OutputView.jsx";
import EvaluationView from "./EvaluationView.jsx";
import { hashFor } from "../lib/routes.js";

/**
 * Coluna de uma versão de comparação já salva (só leitura): saída e nota do candidato.
 * Fonte única para o cache da aba Comparar (`SavedComparison`) e para o detalhe do Histórico (`ComparisonDetail`).
 */
export default function SavedVersionColumn({ version, contentType, meta }) {
  return (
    <article className="compare-col" aria-label={`Versão ${version.prompt_version}`}>
      <h3>Prompt {version.prompt_version}</h3>
      <p className="hint">
        Execução <a href={hashFor("history", version.run_id)}>{version.run_id}</a>
      </p>
      <OutputView
        run={{ content_type: contentType, output: version.output, rendered: version.rendered }}
        confidenceLevels={meta.confidence_levels}
      />
      <EvaluationView title="Avaliação do candidato" evaluation={version.evaluation} rubric={meta.rubric} />
    </article>
  );
}
