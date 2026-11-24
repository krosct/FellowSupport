import RunInfo from "./RunInfo.jsx";
import OutputView from "./OutputView.jsx";
import EvaluationView from "./EvaluationView.jsx";

/**
 * Resultado de uma execução: dados da execução (com o caminho do JSON) e a visualização do conteúdo.
 * Quando o tipo falhou (modo "Todos"), mostra o erro e, se existir, o caminho do JSON de erro. Se a execução já foi
 * avaliada (Comparar), mostra a nota do candidato (`rubric` e `contentTypes` vêm de /api/meta).
 */
export default function RunResult({ item, confidenceLevels, rubric, contentTypes }) {
  if (item.error) {
    return (
      <div className="stack">
        <p className="inline-error" role="alert">
          {item.error.message}
        </p>
        {item.saved_path && (
          <p className="saved-path">
            <span className="summary-label">JSON de erro</span>
            <code>{item.saved_path}</code>
          </p>
        )}
      </div>
    );
  }
  return (
    <div className="stack">
      <RunInfo run={item.run} savedPath={item.saved_path} contentTypes={contentTypes} />
      <OutputView run={item.run} confidenceLevels={confidenceLevels} />
      {rubric && item.run.evaluation && (
        <EvaluationView title="Avaliação do candidato" evaluation={item.run.evaluation} rubric={rubric} />
      )}
    </div>
  );
}
