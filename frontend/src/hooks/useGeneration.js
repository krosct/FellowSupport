import { useCallback, useRef, useState } from "react";
import { generate } from "../api/client.js";
import { useToast } from "../components/Toast.jsx";
import { useConfirmedRequest } from "./useConfirmedRequest.js";

/**
 * Uniformiza a resposta da API em uma lista de itens `{ content_type, saved_path, run, error }`: um tipo
 * responde `{ saved_path, run }` e "Todos" responde `{ results, warning }`. Em "Todos" ficam só os tipos que deram
 * certo; os que falharam aparecem no aviso (`warning`, a mesma frase que a CLI imprime).
 */
function toItems(response) {
  if (response.results) return response.results.filter((item) => !item.error);
  return [{ content_type: response.run.content_type, saved_path: response.saved_path, run: response.run, error: null }];
}

const LOADING = { status: "loading", items: [] };

/**
 * Estado da geração: `idle`, `loading` ou `done` (com `items`, um por tipo gerado).
 * Em "Todos", se só parte dos tipos falhar, mostra o que deu certo e um toast com os tipos que falharam (se todos
 * falharem, a API responde com erro). Em caso de erro mostra um toast e volta a `idle`, sem deixar um resultado antigo na tela. Se a geração substituir
 * entradas do cache, pede a confirmação antes (uma janela só); cancelar devolve a tela ao estado anterior.
 */
export function useGeneration() {
  const toast = useToast();
  const confirmed = useConfirmedRequest();
  const [state, setState] = useState({ status: "idle", items: [] });
  const latest = useRef(state);
  latest.current = state;

  const run = useCallback(
    async (payload) => {
      const before = latest.current;
      setState(LOADING);
      try {
        const response = await confirmed((confirmReplace) => generate({ ...payload, confirm_replace: confirmReplace }), {
          onAsk: (asking) => setState(asking ? before : LOADING),
        });
        setState(response ? { status: "done", items: toItems(response) } : before);
        if (response?.warning) toast.error(response.warning);
      } catch (error) {
        toast.error(error.message);
        setState({ status: "idle", items: [] });
      }
    },
    [toast, confirmed],
  );

  return { ...state, run };
}
