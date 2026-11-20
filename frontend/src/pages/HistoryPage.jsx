import { useCallback, useState } from "react";
import { useRuns } from "../hooks/useRuns.js";
import Section from "../components/Section.jsx";
import RunFilters from "../components/RunFilters.jsx";
import RunList from "../components/RunList.jsx";
import RunDetail from "../components/RunDetail.jsx";

// Filtros vazios: o estado inicial e o resultado de "Limpar".
const NO_FILTERS = { customer_id: "", ticket_id: "", content_type: "", prompt_version: "", status: "" };

/**
 * Aba Histórico: lista as execuções salvas, com filtros simples, e mostra o detalhe de uma. A execução aberta vem
 * do hash (`#/historico/<id>`), então o link de uma execução pode ser copiado e o botão Voltar do navegador funciona.
 */
export default function HistoryPage({ catalog, route, navigate, active }) {
  const [filters, setFilters] = useState(NO_FILTERS);
  const { runId } = route;
  const { status, runs } = useRuns(filters, active && !runId);
  const { meta } = catalog;

  const openRun = useCallback((id) => navigate("history", id), [navigate]);
  const backToList = useCallback(() => navigate("history"), [navigate]);

  if (runId) return <RunDetail runId={runId} meta={meta} onBack={backToList} />;

  return (
    <Section id="history-list" title="Histórico" hint="Execuções salvas, da mais recente para a mais antiga.">
      <div className="stack">
        <RunFilters catalog={catalog} filters={filters} onChange={setFilters} onClear={() => setFilters(NO_FILTERS)} />
        {status === "loading" && runs.length === 0 && <p aria-busy="true">Carregando...</p>}
        {status !== "loading" && runs.length === 0 && <p className="hint">Nenhuma execução encontrada.</p>}
        {runs.length > 0 && (
          <>
            <p className="hint" aria-live="polite">
              {runs.length} {runs.length === 1 ? "execução" : "execuções"}
              {runs.length >= meta.limits.history_limit && ` (limite de ${meta.limits.history_limit})`}
            </p>
            <RunList runs={runs} contentTypes={meta.content_types} onOpen={openRun} />
          </>
        )}
      </div>
    </Section>
  );
}
