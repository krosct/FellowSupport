import { useState } from "react";
import RunResult from "./RunResult.jsx";
import SegmentedControl from "./SegmentedControl.jsx";
import { labelOf } from "../lib/labels.js";

/**
 * Resultado de uma geração: um tipo mostra direto o `RunResult`; "Todos" mostra abas (uma por tipo gerado; os que
 * falharam só aparecem no toast) e a lista com o caminho do JSON de cada execução. Os rótulos vêm de /api/meta.
 */
export default function GenerationResults({ items, meta }) {
  const [selected, setSelected] = useState(items[0]?.content_type);

  if (items.length === 1) return <RunResult item={items[0]} confidenceLevels={meta.confidence_levels} rubric={meta.rubric} contentTypes={meta.content_types} />;

  const tabs = items.map((item) => ({
    value: item.content_type,
    label: labelOf(meta.content_types, item.content_type),
  }));
  const current = items.find((item) => item.content_type === selected) ?? items[0];

  return (
    <div className="stack">
      <ul className="saved-list" aria-label="JSON de cada execução">
        {items.map((item) => (
          <li key={item.content_type}>
            <span className="summary-label">{labelOf(meta.content_types, item.content_type)}</span>
            <code>{item.saved_path}</code>
          </li>
        ))}
      </ul>
      <SegmentedControl options={tabs} value={current.content_type} onChange={setSelected} label="Tipo de conteúdo" wrap />
      <RunResult item={current} confidenceLevels={meta.confidence_levels} rubric={meta.rubric} contentTypes={meta.content_types} />
    </div>
  );
}
