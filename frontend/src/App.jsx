import { ToastProvider } from "./components/Toast.jsx";
import ScenarioPage from "./pages/ScenarioPage.jsx";

/** Raiz do app. Hoje só há a tela de cenário; as abas Gerar, Comparar e Histórico chegam nas próximas etapas. */
export default function App() {
  return (
    <ToastProvider>
      <ScenarioPage />
    </ToastProvider>
  );
}
