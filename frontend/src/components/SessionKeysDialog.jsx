import { useEffect, useId, useRef, useState } from "react";

/**
 * Janela modal (<dialog>) para configurar as chaves de sessão: `openrouter_api_key` (para gerar no provedor real)
 * e `admin_api_key` (para criar/editar/remover clientes, tickets e prompts). Valem só para a sessão atual.
 */
export default function SessionKeysDialog({ open, meta, keys, onSave, onCancel }) {
  const dialogRef = useRef(null);
  const titleId = useId();
  const [draft, setDraft] = useState(keys);

  useEffect(() => {
    if (open) setDraft(keys);
  }, [open, keys]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  const openrouterPlaceholder = meta?.deploy_mode
    ? "Informe sua chave para gerar nesta sessão"
    : meta?.llm?.server_key_configured
      ? "Usando .env local (preencha para sobrescrever)"
      : "Obrigatória se LLM_PROVIDER=openrouter";

  const adminPlaceholder = meta?.admin_protected
    ? "Obrigatória para gerenciar cliente, ticket e prompt"
    : "Não exigida no ambiente local";

  const handleSubmit = (event) => {
    event.preventDefault();
    onSave(draft);
  };

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
            <strong id={titleId}>Chaves da sessão</strong>
          </header>
          <form className="entity-form" onSubmit={handleSubmit}>
            <p className="hint">Valem só para esta sessão do navegador; gerar, comparar e histórico são abertos.</p>
            <label className="form-field">
              openrouter_api_key
              <input
                type="password"
                autoComplete="off"
                value={draft.openrouter_api_key}
                onChange={(e) => setDraft({ ...draft, openrouter_api_key: e.target.value })}
                placeholder={openrouterPlaceholder}
              />
            </label>
            <label className="form-field">
              admin_api_key
              <input
                type="password"
                autoComplete="off"
                value={draft.admin_api_key}
                onChange={(e) => setDraft({ ...draft, admin_api_key: e.target.value })}
                placeholder={adminPlaceholder}
              />
            </label>
            <footer className="dialog-actions">
              <button
                type="button"
                className="secondary outline"
                onClick={() => onSave({ openrouter_api_key: "", admin_api_key: "" })}
              >
                Limpar
              </button>
              <button type="button" className="secondary" onClick={onCancel}>
                Cancelar
              </button>
              <button type="submit">Salvar</button>
            </footer>
          </form>
        </article>
      )}
    </dialog>
  );
}
