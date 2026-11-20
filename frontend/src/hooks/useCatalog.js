import { useCallback, useEffect, useState } from "react";
import { getMeta, getProfiles, getPromptVersions, getTickets } from "../api/client.js";
import { useToast } from "../components/Toast.jsx";

/**
 * Carrega metadados, perfis, tickets e versões de prompt de uma vez. Em caso de erro, mostra um toast e expõe `reload`
 * para o botão "Tentar novamente".
 */
export function useCatalog() {
  const toast = useToast();
  const [state, setState] = useState({ status: "loading", meta: null, profiles: [], tickets: [], versions: [] });

  const load = useCallback(async () => {
    setState((prev) => ({ ...prev, status: "loading" }));
    try {
      const [meta, profiles, tickets, versions] = await Promise.all([
        getMeta(),
        getProfiles(),
        getTickets(),
        getPromptVersions(),
      ]);
      setState({ status: "ready", meta, profiles, tickets, versions });
    } catch (error) {
      toast.error(error.message);
      setState((prev) => ({ ...prev, status: "error" }));
    }
  }, [toast]);

  useEffect(() => {
    load();
  }, [load]);

  return { ...state, reload: load };
}
