import { useEffect, useState } from "react";
import { getComparison } from "../api/client.js";
import { useToast } from "./Toast.jsx";
import Section from "./Section.jsx";
import ProfileBadges from "./ProfileBadges.jsx";
import VersionCarousel from "./VersionCarousel.jsx";
import SavedVersionColumn from "./SavedVersionColumn.jsx";
import ComparisonVerdict from "./ComparisonVerdict.jsx";
import { labelOf } from "../lib/labels.js";

/**
 * Detalhe de uma comparação salva: cenário, vencedor e conclusão e, para cada versão, a saída e a nota do
 * candidato, em carrossel de duas colunas por vez (o mesmo da aba Comparar). Id inexistente mostra um toast e volta.
 */
export default function ComparisonDetail({ comparisonId, meta, onBack }) {
  const toast = useToast();
  const [data, setData] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    getComparison(comparisonId)
      .then((response) => {
        if (!cancelled) setData(response);
      })
      .catch((error) => {
        if (cancelled) return;
        toast.error(error.message);
        onBack();
      });
    return () => {
      cancelled = true;
    };
  }, [comparisonId, toast, onBack]);

  const comparison = data?.comparison;
  const scenario = comparison?.scenario;

  return (
    <div className="stack">
      <div>
        <button type="button" className="secondary outline back-button" onClick={onBack}>
          ← Voltar às comparações
        </button>
      </div>
      <Section
        id="comparison-detail"
        title={scenario ? `${labelOf(meta.content_types, scenario.content_type)} · ${scenario.customer_profile.name}` : "Comparação"}
        hint={scenario?.ticket.title}
      >
        {!comparison && <p aria-busy="true">Carregando...</p>}
        {comparison && (
          <div className="stack">
            <ProfileBadges profile={scenario.customer_profile} enums={meta.enums} />
            <ComparisonVerdict comparison={comparison} savedPath={data.saved_path} rubric={meta.rubric} />
            <VersionCarousel
              key={comparison.comparison_id}
              label="Versões comparadas"
              items={comparison.versions}
              getKey={(version) => version.run_id}
              getLabel={(version) => version.prompt_version}
              render={(version) => <SavedVersionColumn version={version} contentType={scenario.content_type} meta={meta} />}
            />
          </div>
        )}
      </Section>
    </div>
  );
}
