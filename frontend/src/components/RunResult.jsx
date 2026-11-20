import RunInfo from "./RunInfo.jsx";
import OutputView from "./OutputView.jsx";

/**
 * Resultado de uma execução: dados da execução (com o caminho do JSON) e a visualização do conteúdo.
 * Quando o tipo falhou (modo "Todos"), mostra o erro e, se existir, o caminho do JSON de erro.
 */
export default function RunResult({ item, confidenceLevels }) {
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
      <RunInfo run={item.run} savedPath={item.saved_path} />
      <OutputView run={item.run} confidenceLevels={confidenceLevels} />
    </div>
  );
}
