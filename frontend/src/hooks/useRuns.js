import { useCallback, useEffect, useRef, useState } from "react";
import { getRuns } from "../api/client.js";
import { useToast } from "../components/Toast.jsx";

/**
 * Carrega o histórico conforme os filtros, enquanto `enabled`. Refaz a busca quando os filtros mudam ou a aba volta a
 * ficar visível (execuções novas aparecem sem recarregar a página). Erros viram toast; respostas antigas de uma
 * busca já superada são descartadas.
 */
export function useRuns(filters, enabled) {
  const toast = useToast();
  const [state, setState] = useState({ status: "loading", runs: [] });
  const latest = useRef(0);

  const load = useCallback(async () => {
    const request = ++latest.current;
    setState((prev) => ({ ...prev, status: "loading" }));
    try {
      const runs = await getRuns(filters);
      if (request === latest.current) setState({ status: "ready", runs });
    } catch (error) {
      if (request !== latest.current) return;
      toast.error(error.message);
      setState((prev) => ({ ...prev, status: "error" }));
    }
  }, [filters, toast]);

  useEffect(() => {
    if (enabled) load();
  }, [enabled, load]);

  return { ...state, reload: load };
}
