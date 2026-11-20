import Badge from "./Badge.jsx";
import BulletList from "./BulletList.jsx";
import HypothesisCard from "./HypothesisCard.jsx";
import { labelOf } from "../lib/labels.js";

// Cor do selo de confiança pela posição na lista de /api/meta (da menor para a maior), sem repetir os valores.
const CONFIDENCE_KINDS = ["low", "warn", "ok"];

/**
 * Diagnóstico estruturado: hipóteses, evidências disponíveis, informações faltantes, conclusão provável e
 * resumo para o cliente. Reutilizável (Comparar e Histórico usarão o mesmo componente). Os rótulos de
 * confiança vêm de /api/meta (`confidenceLevels`).
 */
export default function DiagnosisView({ diagnosis, confidenceLevels }) {
  const { probable_conclusion: conclusion } = diagnosis;
  const confidenceIndex = confidenceLevels.findIndex((level) => level.value === conclusion.confidence);

  return (
    <div className="diagnosis">
      <section>
        <h3>Hipóteses</h3>
        <div className="hypothesis-list">
          {diagnosis.hypotheses.map((hypothesis) => (
            <HypothesisCard key={hypothesis.id} hypothesis={hypothesis} chosen={hypothesis.id === conclusion.hypothesis_id} />
          ))}
        </div>
      </section>

      <div className="diagnosis-columns">
        <section>
          <h3>Evidências disponíveis</h3>
          <BulletList items={diagnosis.available_evidence} />
        </section>
        <section>
          <h3>Informações faltantes</h3>
          {diagnosis.missing_information.length ? (
            <ul className="missing-list">
              {diagnosis.missing_information.map((info, index) => (
                <li key={index}>
                  <strong>{info.item}</strong>
                  <span className="hint">{info.why_it_matters}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="hint">Nenhuma.</p>
          )}
        </section>
      </div>

      <section className="conclusion">
        <h3>Conclusão provável</h3>
        <div className="conclusion-head">
          <Badge kind="ok">{conclusion.hypothesis_id}</Badge>
          <Badge kind={CONFIDENCE_KINDS[confidenceIndex] ?? "neutral"}>
            Confiança: {labelOf(confidenceLevels, conclusion.confidence)}
          </Badge>
        </div>
        <p>{conclusion.summary}</p>
      </section>

      <section className="customer-summary">
        <h3>Resumo para o cliente</h3>
        <p>{diagnosis.customer_summary}</p>
      </section>
    </div>
  );
}
