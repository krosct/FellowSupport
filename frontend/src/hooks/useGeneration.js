import { useCallback, useState } from "react";
import { generate } from "../api/client.js";
import { useToast } from "../components/Toast.jsx";

/**
 * Estado da geração: `idle`, `loading` ou `done` (com `result = { saved_path, run }`).
 * Em caso de erro mostra um toast e volta a `idle`, sem deixar um resultado antigo na tela.
 */
export function useGeneration() {
  const toast = useToast();
  const [state, setState] = useState({ status: "idle", result: null });

  const run = useCallback(
    async (payload) => {
      setState({ status: "loading", result: null });
      try {
        const result = await generate(payload);
        setState({ status: "done", result });
      } catch (error) {
        toast.error(error.message);
        setState({ status: "idle", result: null });
      }
    },
    [toast],
  );

  return { ...state, run };
}
