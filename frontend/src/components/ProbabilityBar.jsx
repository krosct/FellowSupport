/** Barra de probabilidade (0 a 100). O valor também aparece em texto, para não depender só da cor. */
export default function ProbabilityBar({ value }) {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div className="prob" role="img" aria-label={`Probabilidade ${pct}%`}>
      <div className="prob-track">
        <div className="prob-fill" style={{ width: `${pct}%` }} />
      </div>
      <span className="prob-value">{pct}%</span>
    </div>
  );
}
