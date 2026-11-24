/**
 * Casca dos formulários de cadastro: o `<form>`, o botão de gravar e, ao editar, o de cancelar a edição. Só o botão
 * grava (Enter num campo de uma linha também envia o formulário). Os campos entram como `children`; cada cadastro
 * decide a validade (`canSubmit`) e os rótulos (`addLabel` e `editLabel`).
 */
export default function FormShell({
  editing,
  canSubmit,
  canCancel = editing,
  busy,
  addLabel,
  editLabel,
  cancelLabel,
  onSubmit,
  onCancelEdit,
  children,
}) {
  return (
    <form
      className="entity-form"
      onSubmit={(event) => {
        event.preventDefault();
        if (canSubmit && !busy) onSubmit();
      }}
    >
      {children}
      <div className="form-actions">
        <button type="submit" disabled={!canSubmit || busy} aria-busy={busy}>
          {editing ? editLabel : addLabel}
        </button>
        {canCancel && (
          <button type="button" className="secondary" disabled={busy} onClick={onCancelEdit}>
            {cancelLabel ?? "Cancelar edição"}
          </button>
        )}
      </div>
    </form>
  );
}
