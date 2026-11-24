import Badge from "./Badge.jsx";

/**
 * Resultado da comparação: vencedor (ou empate), total de cada versão, conclusão e o caminho do JSON salvo.
 * Usado ao salvar na aba Comparar e no detalhe de uma comparação do Histórico.
 */
export default function ComparisonVerdict({ comparison, savedPath, rubric }) {
  const { winner, versions, conclusion, conclusion_source: source } = comparison;
  return (
    <section className="callout" data-kind={winner ? "ok" : "warn"} aria-live="polite">
      <h3>{winner ? `Vencedor: ${winner}` : "Empate"}</h3>
      <div className="conclusion-head badges">
        {versions.map((version) => (
          <Badge key={version.prompt_version} kind={version.prompt_version === winner ? "ok" : "neutral"}>
            {version.prompt_version}: {version.total} de {rubric.total_max}
          </Badge>
        ))}
      </div>
      <p>
        {conclusion} <small className="hint">({source})</small>
      </p>
      <p className="saved-path">
        <span className="summary-label">JSON salvo</span>
        <code>{savedPath}</code>
      </p>
    </section>
  );
}
