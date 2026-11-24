import { useEffect, useState } from "react";
import { getRun } from "../api/client.js";
import { useToast } from "./Toast.jsx";
import RunResult from "./RunResult.jsx";
import Section from "./Section.jsx";
import { labelOf } from "../lib/labels.js";

/** Converte a resposta de `GET /api/runs/{id}` no item que `RunResult` já sabe mostrar (o mesmo da geração). */
function toItem({ saved_path: savedPath, run }) {
  return { content_type: run.content_type, saved_path: savedPath, run, error: run.status === "error" ? run.error : null };
}

/**
 * Detalhe de uma execução do histórico, reaproveitando `RunResult` (e, por ele, `RunInfo` e `OutputView`).
 * Id inexistente mostra um toast e volta à lista.
 */
export default function RunDetail({ runId, meta, onBack }) {
  const toast = useToast();
  const [item, setItem] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setItem(null);
    getRun(runId)
      .then((response) => {
        if (!cancelled) setItem(toItem(response));
      })
      .catch((error) => {
        if (cancelled) return;
        toast.error(error.message);
        onBack();
      });
    return () => {
      cancelled = true;
    };
  }, [runId, toast, onBack]);

  return (
    <div className="stack">
      <div>
        <button type="button" className="secondary outline back-button" onClick={onBack}>
          ← Voltar ao histórico
        </button>
      </div>
      <Section id="history-detail" title={item ? labelOf(meta.content_types, item.content_type) : "Execução"}>
        {!item && <p aria-busy="true">Carregando...</p>}
        {item && <RunResult item={item} confidenceLevels={meta.confidence_levels} rubric={meta.rubric} contentTypes={meta.content_types} />}
      </Section>
    </div>
  );
}
