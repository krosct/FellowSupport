import { useCallback } from "react";
import { isCacheReplaceConflict } from "../api/client.js";
import { useConfirmReplace } from "../components/ConfirmReplace.jsx";

/**
 * Envolve uma chamada que pode substituir entradas do cache (ADR 0036). `call(confirmReplace)` é feita primeiro
 * sem confirmação; se a API responder 409, uma janela única lista todas as entradas e, aceita, a **mesma** chamada é
 * repetida com `confirmReplace = true`. Devolve a resposta, ou `null` se o usuário cancelou. Outros erros propagam.
 * `onAsk(true|false)` avisa quando a janela abre e fecha, para a tela não ficar "carregando" enquanto se decide.
 */
export function useConfirmedRequest() {
  const confirmReplace = useConfirmReplace();
  return useCallback(
    async (call, { onAsk } = {}) => {
      try {
        return await call(false);
      } catch (error) {
        if (!isCacheReplaceConflict(error)) throw error;
        onAsk?.(true);
        const accepted = await confirmReplace(error.conflicts);
        onAsk?.(false);
        return accepted ? call(true) : null;
      }
    },
    [confirmReplace],
  );
}
