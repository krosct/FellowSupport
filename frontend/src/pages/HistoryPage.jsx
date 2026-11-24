import { useCallback, useMemo, useState } from "react";
import { useRuns } from "../hooks/useRuns.js";
import { useComparisons } from "../hooks/useComparisons.js";
import Section from "../components/Section.jsx";
import SegmentedControl from "../components/SegmentedControl.jsx";
import RunFilters from "../components/RunFilters.jsx";
import RunList from "../components/RunList.jsx";
import RunDetail from "../components/RunDetail.jsx";
import ComparisonList from "../components/ComparisonList.jsx";
import ComparisonDetail from "../components/ComparisonDetail.jsx";
import Pagination from "../components/Pagination.jsx";

// Filtros vazios: o estado inicial e o resultado de "Limpar".
const NO_FILTERS = { customer_id: "", ticket_id: "", content_type: "", prompt_version: "", status: "", cache_key: "" };

// Visões do Histórico (rótulos de interface; o valor é o `view` da rota).
const VIEWS = [
  { value: "runs", label: "Execuções" },
  { value: "comparisons", label: "Comparações" },
];

/**
 * Aba Histórico: lista as execuções salvas, com filtros, ou as comparações salvas, em páginas (itens por página de
 * /api/meta), e mostra o detalhe de uma.
 * O item aberto vem do hash (`#/historico/<id>` e `#/historico/comparacoes/<id>`), então o link pode ser copiado e o
 * botão Voltar do navegador funciona.
 */
export default function HistoryPage({ catalog, route, navigate, navigateComparisons, active }) {
  const { meta } = catalog;
  const [filters, setFilters] = useState(NO_FILTERS);
  const [runsPage, setRunsPage] = useState({ page: 1, size: meta.limits.history_limit });
  const [comparisonsPage, setComparisonsPage] = useState({ page: 1, size: meta.limits.comparisons_limit });
  const { runId, comparisonId, view } = route;
  const runsQuery = useMemo(
    () => ({ ...filters, limit: runsPage.size, offset: (runsPage.page - 1) * runsPage.size }),
    [filters, runsPage],
  );
  const comparisonsQuery = useMemo(
    () => ({ limit: comparisonsPage.size, offset: (comparisonsPage.page - 1) * comparisonsPage.size }),
    [comparisonsPage],
  );
  const runs = useRuns(runsQuery, active && view === "runs" && !runId);
  const comparisons = useComparisons(comparisonsQuery, active && view === "comparisons" && !comparisonId);

  // Trocar um filtro volta à primeira página (a página atual pode nem existir no novo resultado).
  const changeFilters = (next) => {
    setFilters(next);
    setRunsPage((current) => ({ ...current, page: 1 }));
  };

  const openRun = useCallback((id) => navigate("history", id), [navigate]);
  const backToList = useCallback(() => navigate("history"), [navigate]);
  const openComparison = useCallback((id) => navigateComparisons(id), [navigateComparisons]);
  const backToComparisons = useCallback(() => navigateComparisons(), [navigateComparisons]);

  if (runId) return <RunDetail runId={runId} meta={meta} onBack={backToList} />;
  if (comparisonId) return <ComparisonDetail comparisonId={comparisonId} meta={meta} onBack={backToComparisons} />;

  const changeView = (next) => (next === "comparisons" ? navigateComparisons() : navigate("history"));

  return (
    <Section
      id="history-list"
      title="Histórico"
      hint={view === "runs" ? "Execuções salvas, da mais recente para a mais antiga." : "Comparações salvas, da mais recente para a mais antiga."}
    >
      <div className="stack">
        <SegmentedControl label="O que listar" options={VIEWS} value={view} onChange={changeView} />
        {view === "runs" ? (
          <>
            <RunFilters catalog={catalog} filters={filters} onChange={changeFilters} onClear={() => changeFilters(NO_FILTERS)} />
            {runs.status === "loading" && runs.runs.length === 0 && <p aria-busy="true">Carregando...</p>}
            {runs.status !== "loading" && runs.runs.length === 0 && <p className="hint">Nenhuma execução encontrada.</p>}
            {runs.runs.length > 0 && (
              <>
                <RunList runs={runs.runs} contentTypes={meta.content_types} totalMax={meta.rubric.total_max} onOpen={openRun} />
                <Pagination
                  page={runsPage.page}
                  pageSize={runsPage.size}
                  total={runs.total}
                  pageSizes={meta.limits.page_sizes}
                  onPageChange={(page) => setRunsPage((current) => ({ ...current, page }))}
                  onPageSizeChange={(size) => setRunsPage({ page: 1, size })}
                  singular="execução"
                  plural="execuções"
                />
              </>
            )}
          </>
        ) : (
          <>
            {comparisons.status === "loading" && comparisons.comparisons.length === 0 && <p aria-busy="true">Carregando...</p>}
            {comparisons.status !== "loading" && comparisons.comparisons.length === 0 && (
              <p className="hint">Nenhuma comparação salva.</p>
            )}
            {comparisons.comparisons.length > 0 && (
              <>
                <ComparisonList
                  comparisons={comparisons.comparisons}
                  contentTypes={meta.content_types}
                  totalMax={meta.rubric.total_max}
                  onOpen={openComparison}
                />
                <Pagination
                  page={comparisonsPage.page}
                  pageSize={comparisonsPage.size}
                  total={comparisons.total}
                  pageSizes={meta.limits.page_sizes}
                  onPageChange={(page) => setComparisonsPage((current) => ({ ...current, page }))}
                  onPageSizeChange={(size) => setComparisonsPage({ page: 1, size })}
                  singular="comparação"
                  plural="comparações"
                />
              </>
            )}
          </>
        )}
      </div>
    </Section>
  );
}
