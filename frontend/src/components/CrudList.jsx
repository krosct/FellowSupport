import { useState } from "react";
import ConfirmDialog from "./ConfirmDialog.jsx";

/**
 * Lista de um cadastro (clientes, tickets ou prompts): cada item mostra o resumo (`renderItem`) e os botões
 * opcionais `Novo`, `Editar` e `Remover`. Remover só acontece depois da confirmação numa janela própria (nada de
 * `confirm` nativo). `itemLabel` dá o nome do item para a janela e para os leitores de tela; `editingId` destaca
 * o item em edição e `sourceId` o item usado como base para criar um novo.
 */
export default function CrudList({
  items,
  getId = (item) => item.id,
  itemLabel,
  renderItem,
  editingId,
  sourceId,
  onNew,
  onEdit,
  canEdit = () => true,
  editHint,
  onRemove,
  canRemove = () => true,
  removeHint,
  confirmRemoveText,
  busy,
  label,
  emptyText,
}) {
  const [removing, setRemoving] = useState(null); // item à espera da confirmação

  if (items.length === 0) return <p className="hint">{emptyText}</p>;

  const confirmRemove = async () => {
    if (await onRemove(removing)) setRemoving(null);
  };

  return (
    <>
      <ul className="crud-list" aria-label={label}>
        {items.map((item) => {
          const id = getId(item);
          const editable = canEdit(item);
          const removable = canRemove(item);
          return (
            <li
              key={id}
              className="crud-item"
              data-editing={editingId === id}
              data-source={sourceId === id}
            >
              <div className="crud-item-body">{renderItem(item)}</div>
              <div className="crud-item-actions">
                {onNew && (
                  <button
                    type="button"
                    disabled={busy}
                    aria-label={`Novo a partir de ${itemLabel(item)}`}
                    onClick={() => onNew(item)}
                  >
                    Novo
                  </button>
                )}
                {onEdit && (
                  <button
                    type="button"
                    disabled={busy || !editable}
                    title={editHint ? editHint(item) : undefined}
                    aria-label={`Editar ${itemLabel(item)}`}
                    onClick={() => onEdit(item)}
                  >
                    Editar
                  </button>
                )}
                <button
                  type="button"
                  disabled={busy || !removable}
                  title={removeHint ? removeHint(item) : undefined}
                  aria-label={`Remover ${itemLabel(item)}`}
                  onClick={() => setRemoving(item)}
                >
                  Remover
                </button>
              </div>
            </li>
          );
        })}
      </ul>
      <ConfirmDialog
        open={removing !== null}
        title="Remover?"
        confirmLabel="Remover"
        danger
        onConfirm={confirmRemove}
        onCancel={() => setRemoving(null)}
      >
        <p>
          {removing &&
            (confirmRemoveText
              ? confirmRemoveText(removing)
              : `"${itemLabel(removing)}" sai do catálogo. O histórico não muda.`)}
        </p>
      </ConfirmDialog>
    </>
  );
}
