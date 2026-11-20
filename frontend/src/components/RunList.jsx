import Badge from "./Badge.jsx";
import { formatLatency, formatTimestamp } from "../lib/format.js";
import { labelOf } from "../lib/labels.js";

/**
 * Lista de execuções (da mais recente para a mais antiga). Cada linha é um botão: clicar abre o detalhe.
 * `runs` são os resumos de `GET /api/runs`; os rótulos dos tipos vêm de /api/meta.
 */
export default function RunList({ runs, contentTypes, onOpen }) {
  return (
    <ul className="run-list" aria-label="Execuções">
      {runs.map((run) => (
        <li key={run.run_id}>
          <button type="button" className="run-row" onClick={() => onOpen(run.run_id)}>
            <span className="run-row-main">
              <strong>{labelOf(contentTypes, run.content_type)}</strong>
              <span className="badges">
                <Badge kind={run.status === "ok" ? "ok" : "low"}>{run.status === "ok" ? "Sucesso" : "Erro"}</Badge>
                {run.cache_hit && <Badge kind="cache">Cache</Badge>}
                <Badge kind="neutral">Prompt {run.prompt_version}</Badge>
              </span>
            </span>
            <span className="hint">
              {run.customer_name} · {run.ticket_title} · {formatTimestamp(run.timestamp)} · {formatLatency(run.latency_ms)}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}
