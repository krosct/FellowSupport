import { useCallback, useState } from "react";
import { generate } from "../api/client.js";
import { useToast } from "../components/Toast.jsx";

/**
 * Uniformiza a resposta da API em uma lista de itens `{ content_type, saved_path, run, error }`: um tipo
 * responde `{ saved_path, run }` e "Todos" responde `{ results }`.
 */
function toItems(response) {
  if (response.results) return response.results;
  return [{ content_type: response.run.content_type, saved_path: response.saved_path, run: response.run, error: null }];
}

/**
 * Estado da geração: `idle`, `loading` ou `done` (com `items`, um por tipo gerado).
 * Em caso de erro mostra um toast e volta a `idle`, sem deixar um resultado antigo na tela.
 */
export function useGeneration() {
  const toast = useToast();
  const [state, setState] = useState({ status: "idle", items: [] });

  const run = useCallback(
    async (payload) => {
      setState({ status: "loading", items: [] });
      try {
        const response = await generate(payload);
        setState({ status: "done", items: toItems(response) });
      } catch (error) {
        toast.error(error.message);
        setState({ status: "idle", items: [] });
      }
    },
    [toast],
  );

  return { ...state, run };
}
