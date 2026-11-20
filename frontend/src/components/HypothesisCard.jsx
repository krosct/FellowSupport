import Badge from "./Badge.jsx";
import BulletList from "./BulletList.jsx";
import ProbabilityBar from "./ProbabilityBar.jsx";

/**
 * Uma hipótese do diagnóstico: id, descrição, probabilidade e as evidências a favor e contra.
 * `chosen` destaca a hipótese escolhida na conclusão.
 */
export default function HypothesisCard({ hypothesis, chosen = false }) {
  return (
    <article className="hypothesis" data-chosen={chosen}>
      <header className="hypothesis-head">
        <Badge kind={chosen ? "ok" : "neutral"}>{hypothesis.id}</Badge>
        {chosen && <Badge kind="ok">Conclusão</Badge>}
        <ProbabilityBar value={hypothesis.probability_pct} />
      </header>
      <p className="hypothesis-text">{hypothesis.description}</p>
      <div className="evidence-grid">
        <div>
          <h4>A favor</h4>
          <BulletList items={hypothesis.evidence_for} kind="for" />
        </div>
        <div>
          <h4>Contra</h4>
          <BulletList items={hypothesis.evidence_against} kind="against" />
        </div>
      </div>
    </article>
  );
}
