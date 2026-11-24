import { useCallback, useEffect, useState } from "react";
import { comparisonsHash, hashFor, parseHash } from "../lib/routes.js";

/**
 * Rota atual a partir do hash da URL, sem biblioteca de rotas. `navigate(tab, runId?)` e `navigateComparisons(id?)` trocam o hash; o evento
 * `hashchange` atualiza o estado, então voltar e avançar no navegador também funcionam.
 */
export function useHashRoute() {
  const [route, setRoute] = useState(() => parseHash(window.location.hash));

  useEffect(() => {
    const onChange = () => setRoute(parseHash(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);

  const navigate = useCallback((tab, runId) => {
    window.location.hash = hashFor(tab, runId);
  }, []);

  // Abre a lista de comparações do Histórico, ou uma comparação.
  const navigateComparisons = useCallback((comparisonId) => {
    window.location.hash = comparisonsHash(comparisonId);
  }, []);

  return { route, navigate, navigateComparisons };
}
