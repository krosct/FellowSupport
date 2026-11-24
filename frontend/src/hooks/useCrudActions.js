import { useCallback, useState } from "react";
import { useToast } from "../components/Toast.jsx";

/**
 * Criar, editar e remover itens do catálogo (clientes ou tickets). `api` traz as chamadas e as mensagens:
 * `{ create(payload), update(id, payload), remove(id), created, updated, removed }`. Depois de cada chamada relê a lista
 * (`refresh`, do `useCatalog`) para todas as abas verem a mudança. Os erros viram toast; `save` devolve o item salvo e
 * `remove` devolve `true`, ou `null`/`false` se falhou, para a tela decidir se limpa o formulário. `busy` trava os
 * botões durante a chamada.
 */
export function useCrudActions(api, refresh) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);

  // Roda a chamada com `busy` ligado, relê a lista e avisa; em erro mostra o toast e devolve `failure`.
  const run = useCallback(
    async (call, message, success, failure) => {
      setBusy(true);
      try {
        const result = await call();
        await refresh();
        toast.info(message);
        return success(result);
      } catch (error) {
        toast.error(error.message);
        return failure;
      } finally {
        setBusy(false);
      }
    },
    [refresh, toast],
  );

  /** Cria (rascunho sem `id`) ou edita (com `id`). O `id` não vai no corpo: o servidor decide o dele. */
  const save = useCallback(
    ({ id, ...payload }) =>
      run(
        () => (id ? api.update(id, payload) : api.create(payload)),
        id ? api.updated : api.created,
        (item) => item,
        null,
      ),
    [api, run],
  );

  /** Remove o item pelo id. */
  const remove = useCallback((id) => run(() => api.remove(id), api.removed, () => true, false), [api, run]);

  return { busy, save, remove };
}
