import Badge from "./Badge.jsx";
import { formatLatency, shortHash } from "../lib/format.js";

/** Dados da execução: cliente, ticket, versão do prompt, modelo, latência e onde o JSON foi salvo. */
export default function RunInfo({ run, savedPath }) {
  return (
    <div className="run-info">
      <div className="badges">
        <Badge kind="neutral">Prompt {run.prompt_version}</Badge>
        <Badge kind="neutral">{run.model_used || run.model}</Badge>
        <Badge kind="neutral">{formatLatency(run.latency_ms)}</Badge>
        <Badge kind="neutral">Provedor: {run.provider}</Badge>
        {run.attempts > 1 && <Badge kind="warn">Reparado</Badge>}
      </div>
      <p className="hint">
        {run.customer_profile.name} · {run.ticket.title} · hash {shortHash(run.prompt_sha256)}
      </p>
      <p className="saved-path">
        <span className="summary-label">JSON salvo</span>
        <code>{savedPath}</code>
      </p>
    </div>
  );
}
