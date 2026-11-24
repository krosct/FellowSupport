import { useCallback, useEffect, useRef, useState } from "react";
import { getRuns } from "../api/client.js";
import { useToast } from "../components/Toast.jsx";

/**
 * Carrega uma página do histórico conforme os filtros (com `limit` e `offset`), enquanto `enabled`; `total` é o
 * total de todas as páginas. Refaz a busca quando os filtros mudam ou a aba volta a
 * ficar visível (execuções novas aparecem sem recarregar a página). Erros viram toast; respostas antigas de uma
 * busca já superada são descartadas.
 */
export function useRuns(filters, enabled) {
  const toast = useToast();
  const [state, setState] = useState({ status: "loading", runs: [], total: 0 });
  const latest = useRef(0);

  const load = useCallback(async () => {
    const request = ++latest.current;
    setState((prev) => ({ ...prev, status: "loading" }));
    try {
      const page = await getRuns(filters);
      if (request === latest.current) setState({ status: "ready", runs: page.items, total: page.total });
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
