import { useRef, useState } from "react";
import CrudList from "./CrudList.jsx";
import FormShell from "./FormShell.jsx";
import Section from "./Section.jsx";

/**
 * Tela de CRUD simples de um cadastro (clientes ou tickets): lista à esquerda e formulário à direita. Serve aos dois
 * cadastros; cada um diz só o que muda (`texts`, os itens, o rascunho vazio, os campos e a validade).
 * O rascunho só vira item quando o botão do formulário é apertado; Editar copia o item para o formulário e leva o
 * foco até ele, e depois de gravar o formulário volta vazio.
 */
export default function CatalogCrud({ id, texts, items, itemLabel, renderItem, emptyDraft, toDraft, isValid, renderFields, actions }) {
  const [draft, setDraft] = useState(emptyDraft);
  const formRef = useRef(null);
  const editing = draft.id != null;

  const handleEdit = (item) => {
    setDraft(toDraft(item));
    // Em telas estreitas o formulário fica abaixo da lista: leva a tela e o foco até ele.
    formRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    formRef.current?.querySelector("input, textarea, select")?.focus({ preventScroll: true });
  };

  const handleSubmit = async () => {
    if (await actions.save(draft)) setDraft(emptyDraft);
  };

  const handleRemove = async (item) => {
    const removed = await actions.remove(item.id);
    if (removed && draft.id === item.id) setDraft(emptyDraft); // não deixa editando um item que não existe mais
    return removed;
  };

  return (
    <div className="crud-layout">
      <Section id={`${id}-list`} title={texts.listTitle} hint={texts.listHint}>
        <CrudList
          items={items}
          itemLabel={itemLabel}
          renderItem={renderItem}
          editingId={draft.id}
          onEdit={handleEdit}
          onRemove={handleRemove}
          busy={actions.busy}
          label={texts.listTitle}
          emptyText={texts.empty}
        />
      </Section>
      <div ref={formRef} className="crud-form">
        <Section id={`${id}-form`} title={editing ? texts.editTitle : texts.addTitle}>
          <FormShell
            editing={editing}
            canSubmit={isValid(draft)}
            busy={actions.busy}
            addLabel={texts.addButton}
            editLabel={texts.editButton}
            onSubmit={handleSubmit}
            onCancelEdit={() => setDraft(emptyDraft)}
          >
            {renderFields(draft, setDraft)}
          </FormShell>
        </Section>
      </div>
    </div>
  );
}
