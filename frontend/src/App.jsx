import { ToastProvider } from "./components/Toast.jsx";
import Header from "./components/Header.jsx";
import SegmentedControl from "./components/SegmentedControl.jsx";
import { useCatalog } from "./hooks/useCatalog.js";
import { useHashRoute } from "./hooks/useHashRoute.js";
import { TABS } from "./lib/routes.js";
import ScenarioPage from "./pages/ScenarioPage.jsx";
import HistoryPage from "./pages/HistoryPage.jsx";

/**
 * Casca do app: cabeçalho com as abas (rota por hash, sem react-router), carga do catálogo e as páginas.
 * As duas páginas ficam montadas e só uma aparece: trocar de aba não perde o cenário nem o resultado da geração.
 */
function Shell() {
  const catalog = useCatalog();
  const { route, navigate } = useHashRoute();

  return (
    <>
      <Header
        llm={catalog.meta?.llm}
        nav={<SegmentedControl label="Seções" options={TABS} value={route.tab} onChange={(tab) => navigate(tab)} />}
      />
      <main className="container">
        {catalog.status === "loading" && <p aria-busy="true">Carregando catálogo...</p>}

        {catalog.status === "error" && (
          <div className="panel error-panel" role="alert">
            <p>Não foi possível carregar o catálogo.</p>
            <button type="button" onClick={catalog.reload}>
              Tentar novamente
            </button>
          </div>
        )}

        {catalog.status === "ready" && (
          <>
            <div hidden={route.tab !== "generate"}>
              <ScenarioPage catalog={catalog} />
            </div>
            <div hidden={route.tab !== "history"} className="history-page">
              <HistoryPage catalog={catalog} route={route} navigate={navigate} active={route.tab === "history"} />
            </div>
          </>
        )}
      </main>
    </>
  );
}

/** Raiz do app. A aba Comparar chega na Etapa 4. */
export default function App() {
  return (
    <ToastProvider>
      <Shell />
    </ToastProvider>
  );
}
