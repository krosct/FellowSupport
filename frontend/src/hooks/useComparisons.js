import { useCallback, useEffect, useRef, useState } from "react";
import { getComparisons } from "../api/client.js";
import { useToast } from "../components/Toast.jsx";

/**
 * Carrega uma página das comparações salvas (`page`: `{ limit, offset }`; `total` é o de todas as páginas) enquanto
 * `enabled` (e de novo quando a aba volta a ficar visível, para uma comparação
 * recém-salva aparecer). Erros viram toast; respostas de uma busca já superada são descartadas.
 */
export function useComparisons(page, enabled) {
  const toast = useToast();
  const [state, setState] = useState({ status: "loading", comparisons: [], total: 0 });
  const latest = useRef(0);

  const load = useCallback(async () => {
    const request = ++latest.current;
    setState((prev) => ({ ...prev, status: "loading" }));
    try {
      const result = await getComparisons(page);
      if (request === latest.current) setState({ status: "ready", comparisons: result.items, total: result.total });
    } catch (error) {
      if (request !== latest.current) return;
      toast.error(error.message);
      setState((prev) => ({ ...prev, status: "error" }));
    }
  }, [page, toast]);

  useEffect(() => {
    if (enabled) load();
  }, [enabled, load]);

  return { ...state, reload: load };
}
