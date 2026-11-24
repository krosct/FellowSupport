import { useCallback, useEffect, useState } from "react";
import { getMeta, getProfiles, getPromptVersions, getTickets } from "../api/client.js";
import { useToast } from "../components/Toast.jsx";

/**
 * Carrega metadados, perfis, tickets e versões de prompt de uma vez. Em caso de erro, mostra um toast e expõe `reload`
 * para o botão "Tentar novamente". `refreshProfiles` e `refreshTickets` atualizam só a lista depois de criar, editar ou remover.
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

  // Relê só uma lista (`key`: "profiles" ou "tickets"), sem voltar a `status: "loading"`: as páginas continuam
  // montadas e não perdem o que o usuário preencheu. Devolve a lista nova (ou `null` se falhar, com o erro no toast).
  const refreshList = useCallback(
    async (key, fetchList) => {
      try {
        const list = await fetchList();
        setState((prev) => ({ ...prev, [key]: list }));
        return list;
      } catch (error) {
        toast.error(error.message);
        return null;
      }
    },
    [toast],
  );
  const refreshProfiles = useCallback(() => refreshList("profiles", getProfiles), [refreshList]);
  const refreshTickets = useCallback(() => refreshList("tickets", getTickets), [refreshList]);
  // Atualizar prompts também relê /api/meta porque `default_prompt_version` acompanha a maior versão (ADR 0039).
  const refreshPrompts = useCallback(async () => {
    try {
      const [versions, meta] = await Promise.all([getPromptVersions(), getMeta()]);
      setState((prev) => ({ ...prev, versions, meta }));
      return versions;
    } catch (error) {
      toast.error(error.message);
      return null;
    }
  }, [toast]);

  return { ...state, reload: load, refreshProfiles, refreshTickets, refreshPrompts };
}
