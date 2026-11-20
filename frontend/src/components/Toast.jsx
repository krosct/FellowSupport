import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";

// Tempo até o toast sumir sozinho, em milissegundos.
const TOAST_DURATION_MS = 7000;

const ToastContext = createContext(null);

/**
 * Provedor de toasts: substitui `alert`, `confirm` e `prompt`, que são proibidos no projeto.
 * Erros usam role="alert" (lido de imediato por leitores de tela); os demais, role="status".
 */
export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const push = useCallback(
    (kind, message) => {
      const id = nextId.current++;
      setToasts((current) => [...current, { id, kind, message }]);
      setTimeout(() => dismiss(id), TOAST_DURATION_MS);
    },
    [dismiss],
  );

  // A referência é estável: componentes podem usá-la em dependências de efeitos.
  const api = useMemo(
    () => ({
      error: (message) => push("error", message),
      info: (message) => push("info", message),
    }),
    [push],
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="toast-region" aria-live="polite">
        {toasts.map((toast) => (
          <div key={toast.id} className="toast" data-kind={toast.kind} role={toast.kind === "error" ? "alert" : "status"}>
            <span className="toast-message">{toast.message}</span>
            <button type="button" className="toast-close" aria-label="Fechar aviso" onClick={() => dismiss(toast.id)}>
              ×
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

/** Acesso ao toast: `const toast = useToast(); toast.error("mensagem")`. */
export function useToast() {
  const context = useContext(ToastContext);
  if (!context) throw new Error("useToast precisa estar dentro de <ToastProvider>.");
  return context;
}
