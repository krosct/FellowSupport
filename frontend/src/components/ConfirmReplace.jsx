import { createContext, useCallback, useContext, useRef, useState } from "react";
import { formatTimestamp } from "../lib/format.js";
import { labelOf } from "../lib/labels.js";
import ConfirmDialog from "./ConfirmDialog.jsx";

const ConfirmReplaceContext = createContext(null);

/** Uma linha da lista: o que será trocado e qual entrada de cache vale hoje. */
function ConflictItem({ conflict, contentTypes }) {
  const what = `${labelOf(contentTypes, conflict.content_type)} ${conflict.prompt_version}`;
  const when = conflict.created_at ? ` · ${formatTimestamp(conflict.created_at)}` : "";
  return (
    <li>
      <strong>{what}</strong>
      <small className="hint">
        {" origem atual: "}
        {conflict.run_id}
        {when}
      </small>
    </li>
  );
}

/**
 * Provedor da confirmação de substituição do cache (ADR 0036). Substitui `confirm`, proibido no projeto. Uma única
 * janela lista **todas** as entradas que o pedido trocaria; `confirmReplace(conflicts)` devolve uma Promise que
 * resolve `true` (substituir) ou `false` (cancelar, Esc ou clique fora).
 */
export function ConfirmReplaceProvider({ contentTypes, children }) {
  const [pending, setPending] = useState(null);
  const pendingRef = useRef(null); // o mesmo pedido de `pending`, para responder fora do ciclo de renderização

  const confirmReplace = useCallback(
    (conflicts) =>
      new Promise((resolve) => {
        pendingRef.current = { conflicts, resolve };
        setPending(pendingRef.current);
      }),
    [],
  );

  const answer = useCallback((accepted) => {
    pendingRef.current?.resolve(accepted);
    pendingRef.current = null;
    setPending(null);
  }, []);

  const count = pending?.conflicts.length ?? 0;

  return (
    <ConfirmReplaceContext.Provider value={confirmReplace}>
      {children}
      <ConfirmDialog
        open={pending !== null}
        title="Substituir o cache?"
        confirmLabel="Substituir e continuar"
        onConfirm={() => answer(true)}
        onCancel={() => answer(false)}
      >
        {pending && (
          <>
            <p>
              {count === 1 ? "Esta entrada do cache será substituída" : `Estas ${count} entradas do cache serão substituídas`} pela nova geração:
            </p>
            <ul className="replace-list">
              {pending.conflicts.map((conflict) => (
                <ConflictItem
                  key={`${conflict.content_type}-${conflict.prompt_version}-${conflict.run_id}`}
                  conflict={conflict}
                  contentTypes={contentTypes}
                />
              ))}
            </ul>
          </>
        )}
      </ConfirmDialog>
    </ConfirmReplaceContext.Provider>
  );
}

/** Acesso à janela: `const confirmReplace = useConfirmReplace(); const ok = await confirmReplace(conflicts);`. */
export function useConfirmReplace() {
  const context = useContext(ConfirmReplaceContext);
  if (!context) throw new Error("useConfirmReplace precisa estar dentro de <ConfirmReplaceProvider>.");
  return context;
}
