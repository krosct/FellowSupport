import Badge from "./Badge.jsx";
import { formatTimestamp } from "../lib/format.js";
import { labelOf } from "../lib/labels.js";

/**
 * Lista de comparações salvas (da mais recente para a mais antiga). Cada linha é um botão que abre o detalhe.
 * `comparisons` são os resumos de `GET /api/comparisons`; os rótulos dos tipos vêm de /api/meta.
 */
export default function ComparisonList({ comparisons, contentTypes, totalMax, onOpen }) {
  return (
    <ul className="run-list" aria-label="Comparações">
      {comparisons.map((item) => (
        <li key={item.comparison_id}>
          <button type="button" className="run-row" onClick={() => onOpen(item.comparison_id)}>
            <span className="run-row-main">
              <strong>{labelOf(contentTypes, item.content_type)}</strong>
              <span className="badges">
                <Badge kind={item.winner ? "ok" : "warn"}>{item.winner ? `Vencedor ${item.winner}` : "Empate"}</Badge>
                {item.versions.map((version) => (
                  <Badge key={version.prompt_version} kind="neutral">
                    {version.prompt_version}: {version.total}/{totalMax}
                  </Badge>
                ))}
              </span>
            </span>
            <span className="hint">
              {item.customer_name} · {item.ticket_title} · {formatTimestamp(item.created_at)}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}
