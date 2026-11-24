import { useEffect, useId, useRef } from "react";

/**
 * Janela de confirmação modal (<dialog> nativo), no lugar de `confirm`, proibido no projeto. Controlada: quem usa guarda
 * `open` e responde a `onConfirm` e `onCancel` (botão Cancelar, Esc ou clique fora). `showModal` dá foco preso na
 * janela e inércia no restante da página. `danger` pinta o botão de confirmar como ação destrutiva. Com `declineLabel`
 * e `onDecline`, o botão secundário vira uma segunda escolha (ex.: "Comparar novamente") e só Esc e o clique fora
 * chamam `onCancel`.
 */
export default function ConfirmDialog({
  open,
  title,
  confirmLabel,
  cancelLabel = "Cancelar",
  danger = false,
  declineLabel,
  onDecline,
  onConfirm,
  onCancel,
  children,
}) {
  const dialogRef = useRef(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault();
        onCancel();
      }}
      onClick={(event) => {
        if (event.target === dialogRef.current) onCancel();
      }}
    >
      {open && (
        <article>
          <header>
            <strong id={titleId}>{title}</strong>
          </header>
          {children}
          <footer>
            <button type="button" className="secondary" onClick={declineLabel ? onDecline : onCancel}>
              {declineLabel ?? cancelLabel}
            </button>
            <button type="button" className={danger ? "danger" : undefined} onClick={onConfirm}>
              {confirmLabel}
            </button>
          </footer>
        </article>
      )}
    </dialog>
  );
}
