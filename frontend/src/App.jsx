import { useState } from "react";
import { getSessionKeys, setSessionKeys } from "./api/client.js";
import { ToastProvider, useToast } from "./components/Toast.jsx";
import { ConfirmReplaceProvider } from "./components/ConfirmReplace.jsx";
import Header from "./components/Header.jsx";
import SegmentedControl from "./components/SegmentedControl.jsx";
import SessionKeysDialog from "./components/SessionKeysDialog.jsx";
import { useCatalog } from "./hooks/useCatalog.js";
import { useHashRoute } from "./hooks/useHashRoute.js";
import { TABS } from "./lib/routes.js";
import ProfilesPage from "./pages/ProfilesPage.jsx";
import TicketsPage from "./pages/TicketsPage.jsx";
import PromptsPage from "./pages/PromptsPage.jsx";
import ScenarioPage from "./pages/ScenarioPage.jsx";
import ComparePage from "./pages/ComparePage.jsx";
import HistoryPage from "./pages/HistoryPage.jsx";

/**
 * Casca do app: cabeçalho com as abas (rota por hash, sem react-router), carga do catálogo e as páginas.
 * As páginas ficam montadas e só uma aparece: trocar de aba não perde o cenário, o resultado da geração, o rascunho
 * dos formulários de cadastro nem as notas já preenchidas na comparação.
 */
function Shell() {
  const catalog = useCatalog();
  const toast = useToast();
  const { route, navigate, navigateComparisons } = useHashRoute();
  const [keysOpen, setKeysOpen] = useState(false);
  const [keys, setKeys] = useState(() => getSessionKeys());

  const handleSaveKeys = (nextKeys) => {
    const saved = setSessionKeys(nextKeys);
    setKeys(saved);
    setKeysOpen(false);
    const hasAny = Boolean(saved.openrouter_api_key || saved.admin_api_key);
    toast.info(hasAny ? "Chaves salvas para esta sessão." : "Chaves da sessão limpas.");
  };

  return (
    <>
      <Header
        llm={catalog.meta?.llm}
        hasSessionKeys={Boolean(keys.openrouter_api_key || keys.admin_api_key)}
        onOpenKeys={() => setKeysOpen(true)}
        nav={<SegmentedControl label="Seções" options={TABS} value={route.tab} onChange={(tab) => navigate(tab)} />}
      />
      <SessionKeysDialog
        open={keysOpen}
        meta={catalog.meta}
        keys={keys}
        onSave={handleSaveKeys}
        onCancel={() => setKeysOpen(false)}
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
          <ConfirmReplaceProvider contentTypes={catalog.meta.content_types}>
            <div hidden={route.tab !== "clients"}>
              <ProfilesPage catalog={catalog} />
            </div>
            <div hidden={route.tab !== "tickets"}>
              <TicketsPage catalog={catalog} />
            </div>
            <div hidden={route.tab !== "prompts"}>
              <PromptsPage catalog={catalog} />
            </div>
            <div hidden={route.tab !== "generate"}>
              <ScenarioPage catalog={catalog} />
            </div>
            <div hidden={route.tab !== "compare"}>
              <ComparePage catalog={catalog} active={route.tab === "compare"} />
            </div>
            <div hidden={route.tab !== "history"} className="history-page">
              <HistoryPage
                catalog={catalog}
                route={route}
                navigate={navigate}
                navigateComparisons={navigateComparisons}
                active={route.tab === "history"}
              />
            </div>
          </ConfirmReplaceProvider>
        )}
      </main>
    </>
  );
}

/** Raiz do app. */
export default function App() {
  return (
    <ToastProvider>
      <Shell />
    </ToastProvider>
  );
}
