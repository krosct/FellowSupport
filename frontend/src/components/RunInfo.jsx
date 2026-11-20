import Badge from "./Badge.jsx";
import { formatLatency, formatTimestamp, shortHash } from "../lib/format.js";
import { hashFor } from "../lib/routes.js";

/**
 * Dados da execução: cliente, ticket, versão do prompt, modelo, latência e onde o JSON foi salvo. Num acerto de
 * cache mostra o selo "Cache" com a latência (no lugar do selo de latência comum) e leva à execução de origem.
 */
export default function RunInfo({ run, savedPath }) {
  return (
    <div className="run-info">
      <div className="badges">
        {run.cache_hit && <Badge kind="cache">Cache · {formatLatency(run.latency_ms)}</Badge>}
        <Badge kind="neutral">Prompt {run.prompt_version}</Badge>
        <Badge kind="neutral">{run.model_used || run.model}</Badge>
        {!run.cache_hit && <Badge kind="neutral">{formatLatency(run.latency_ms)}</Badge>}
        <Badge kind="neutral">Provedor: {run.provider}</Badge>
        {run.attempts > 1 && <Badge kind="warn">Reparado</Badge>}
      </div>
      <p className="hint">
        {run.customer_profile.name} · {run.ticket.title} · hash {shortHash(run.prompt_sha256)}
      </p>
      <p className="hint">
        Execução {run.run_id} · {formatTimestamp(run.timestamp)}
        {run.cache_hit && run.source_run_id && (
          <>
            {" "}
            · origem <a href={hashFor("history", run.source_run_id)}>{run.source_run_id}</a>
          </>
        )}
      </p>
      <p className="saved-path">
        <span className="summary-label">JSON salvo</span>
        <code>{savedPath}</code>
      </p>
    </div>
  );
}
