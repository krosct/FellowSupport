import Badge from "./Badge.jsx";
import VersionCarousel from "./VersionCarousel.jsx";
import ComparisonVerdict from "./ComparisonVerdict.jsx";
import SavedVersionColumn from "./SavedVersionColumn.jsx";
import { formatTimestamp } from "../lib/format.js";

/**
 * Comparação já salva (carregada pela janela da aba Comparar): veredito e, por versão, a saída e a nota do
 * candidato, só para leitura. Mesmos componentes do detalhe do Histórico (`ComparisonDetail`).
 */
export default function SavedComparison({ data, meta }) {
  const { comparison, saved_path: savedPath } = data;
  const { scenario } = comparison;
  return (
    <div className="stack">
      <div className="badges">
        <Badge kind="cache">Comparação salva</Badge>
        <Badge kind="neutral">{comparison.comparison_id}</Badge>
        <Badge kind="neutral">{formatTimestamp(comparison.created_at)}</Badge>
      </div>
      <ComparisonVerdict comparison={comparison} savedPath={savedPath} rubric={meta.rubric} />
      <VersionCarousel
        key={comparison.comparison_id}
        label="Versões comparadas"
        items={comparison.versions}
        getKey={(version) => version.run_id}
        getLabel={(version) => version.prompt_version}
        render={(version) => <SavedVersionColumn version={version} contentType={scenario.content_type} meta={meta} />}
      />
    </div>
  );
}
