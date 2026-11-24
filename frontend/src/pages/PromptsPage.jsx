import { useRef, useState } from "react";
import { createPrompt, deletePrompt, getPrompt } from "../api/client.js";
import Badge from "../components/Badge.jsx";
import CrudList from "../components/CrudList.jsx";
import FormShell from "../components/FormShell.jsx";
import Section from "../components/Section.jsx";
import TextField from "../components/TextField.jsx";
import { useToast } from "../components/Toast.jsx";
import { useCrudActions } from "../hooks/useCrudActions.js";

const API = {
  create: createPrompt,
  remove: deletePrompt,
  created: "Prompt criado com hash atualizado.",
  removed: "Prompt removido.",
};

const FILE_ORDER = [
  "system.md",
  "context.md",
  "diagnosis.md",
  "resolution_steps.md",
  "clarifying_questions.md",
  "flow_summary.md",
  "repair.md",
  "adaptation.json",
];

function sortFileNames(files) {
  const rank = new Map(FILE_ORDER.map((name, index) => [name, index]));
  return Object.keys(files).sort((a, b) => {
    const ra = rank.get(a) ?? FILE_ORDER.length;
    const rb = rank.get(b) ?? FILE_ORDER.length;
    return ra !== rb ? ra - rb : a.localeCompare(b);
  });
}

function focusForm(formRef) {
  formRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  formRef.current?.querySelector("input, textarea, select")?.focus({ preventScroll: true });
}

/**
 * Aba Prompt: CRUD de versões de prompt (`prompts/vN/`).
 * Só permite criar uma nova versão clicando em "Novo" em uma versão existente (source/base), preenchendo todos
 * os dados e arquivos no formulário à direita. A versão base `v1` não pode ser editada nem removida.
 */
export default function PromptsPage({ catalog }) {
  const { meta, versions, refreshPrompts } = catalog;
  const actions = useCrudActions(API, refreshPrompts);
  const toast = useToast();
  const [draft, setDraft] = useState(null);
  const [activeFile, setActiveFile] = useState("");
  const [loadingDetail, setLoadingDetail] = useState(false);
  const formRef = useRef(null);

  const baseVersion = meta.limits.base_prompt_version;

  const openFromVersion = async (item) => {
    setLoadingDetail(true);
    try {
      const detail = await getPrompt(item.version);
      const fileNames = sortFileNames(detail.files);
      setDraft({
        based_on: detail.version,
        description: detail.description,
        changes: detail.changes.map((c) => ({ ...c })),
        files: { ...detail.files },
      });
      setActiveFile(fileNames[0] ?? "");
      requestAnimationFrame(() => focusForm(formRef));
    } catch (error) {
      toast.error(error.message);
    } finally {
      setLoadingDetail(false);
    }
  };

  const handleSubmit = async () => {
    if (!draft) return;
    const payload = {
      id: null,
      based_on: draft.based_on,
      description: draft.description,
      changes: draft.changes,
      files: draft.files,
    };
    if (await actions.save(payload)) {
      setDraft(null);
      setActiveFile("");
    }
  };

  const handleRemove = async (item) => {
    const removed = await actions.remove(item.version);
    if (removed && draft?.based_on === item.version) {
      setDraft(null);
      setActiveFile("");
    }
    return removed;
  };

  const fileNames = draft ? sortFileNames(draft.files) : [];
  const currentFile = draft && draft.files[activeFile] !== undefined ? activeFile : fileNames[0] ?? "";

  const isValid =
    draft !== null &&
    Boolean(draft.based_on) &&
    draft.description.trim() !== "" &&
    fileNames.length > 0 &&
    fileNames.every((name) => (draft.files[name] ?? "").trim() !== "") &&
    draft.changes.every((c) => c.what.trim() !== "" && c.why.trim() !== "" && c.expected_effect.trim() !== "");

  const updateChange = (index, field, value) => {
    const next = draft.changes.map((item, i) => (i === index ? { ...item, [field]: value } : item));
    setDraft({ ...draft, changes: next });
  };

  const addChange = () => {
    setDraft({ ...draft, changes: [...draft.changes, { what: "", why: "", expected_effect: "" }] });
  };

  const removeChange = (index) => {
    setDraft({ ...draft, changes: draft.changes.filter((_, i) => i !== index) });
  };

  return (
    <div className="crud-layout prompt-crud-layout">
      <Section id="prompts-list" title="Prompts" hint="Versões usadas nas abas Gerar e Comparar.">
        <CrudList
          items={versions}
          getId={(item) => item.version}
          itemLabel={(item) => item.version}
          renderItem={(item) => (
            <>
              <div className="prompt-item-head">
                <strong>{item.version}</strong>
                <div className="badges">
                  {item.is_default && <Badge kind="ok">padrão</Badge>}
                  <Badge kind="neutral">{item.based_on ? `base: ${item.based_on}` : "linha de base"}</Badge>
                  <Badge>{item.content_sha256.slice(0, 12)}</Badge>
                </div>
              </div>
              <p className="hint crud-excerpt">{item.description}</p>
            </>
          )}
          sourceId={draft?.based_on ?? null}
          onNew={(item) => openFromVersion(item)}
          onRemove={handleRemove}
          canRemove={(item) => item.version !== baseVersion}
          removeHint={(item) =>
            item.version === baseVersion ? `A versão base ${baseVersion} não pode ser removida.` : undefined
          }
          confirmRemoveText={(item) => `A versão "${item.version}" e sua pasta serão removidas. O histórico não muda.`}
          busy={actions.busy || loadingDetail}
          label="Prompts"
          emptyText="Nenhuma versão de prompt encontrada."
        />
      </Section>

      <div ref={formRef} className="crud-form">
        {loadingDetail ? (
          <Section id="prompts-form" title="Carregando prompt...">
            <p className="hint" aria-busy="true">
              Carregando metadados e arquivos...
            </p>
          </Section>
        ) : draft === null ? (
          <Section id="prompts-form" title="Prompt">
            <p className="hint">
              Versões são imutáveis. Clique em <strong>Novo</strong> em uma versão da lista para criar a próxima a
              partir dela.
            </p>
          </Section>
        ) : (
          <Section id="prompts-form" title={`Novo prompt (base: ${draft.based_on})`}>
            <FormShell
              editing={false}
              canSubmit={isValid}
              canCancel
              busy={actions.busy}
              addLabel="Criar prompt"
              cancelLabel="Cancelar"
              onSubmit={handleSubmit}
              onCancelEdit={() => {
                setDraft(null);
                setActiveFile("");
              }}
            >
              <div className="badges">
                <Badge kind="neutral">Source (base): {draft.based_on}</Badge>
              </div>

              <TextField
                label="Descrição"
                multiline
                rows={3}
                value={draft.description}
                onChange={(description) => setDraft({ ...draft, description })}
                maxLength={meta.limits.max_prompt_description_chars}
                placeholder="Resumo do objetivo desta versão de prompt"
              />

              <div className="prompt-files-block">
                <span className="summary-label">Arquivos do prompt ({fileNames.length})</span>

                <div className="prompt-file-tabs" role="tablist" aria-label="Arquivos do prompt">
                  {fileNames.map((name) => (
                    <button
                      key={name}
                      type="button"
                      role="tab"
                      aria-selected={currentFile === name}
                      className="prompt-file-tab"
                      data-active={currentFile === name}
                      data-empty={(draft.files[name] ?? "").trim() === ""}
                      onClick={() => setActiveFile(name)}
                    >
                      {name}
                    </button>
                  ))}
                </div>

                {currentFile && (
                  <TextField
                    label={`Conteúdo de ${currentFile}`}
                    multiline
                    rows={10}
                    className="prompt-file-editor"
                    value={draft.files[currentFile] ?? ""}
                    onChange={(content) =>
                      setDraft({ ...draft, files: { ...draft.files, [currentFile]: content } })
                    }
                    maxLength={meta.limits.max_prompt_file_chars}
                    placeholder={`Texto de ${currentFile}...`}
                  />
                )}
              </div>

              <div className="prompt-changes-block">
                <div className="prompt-section-head">
                  <span className="summary-label">Mudanças ({draft.changes.length})</span>
                  <button
                    type="button"
                    className="secondary outline prompt-small-btn"
                    disabled={actions.busy}
                    onClick={addChange}
                  >
                    + Mudança
                  </button>
                </div>

                {draft.changes.length === 0 ? (
                  <p className="hint">Nenhuma mudança registrada.</p>
                ) : (
                  <div className="stack">
                    {draft.changes.map((change, index) => (
                      <div key={index} className="prompt-change-card">
                        <div className="prompt-section-head">
                          <strong>Mudança #{index + 1}</strong>
                          <button
                            type="button"
                            className="secondary outline prompt-small-btn"
                            disabled={actions.busy}
                            aria-label={`Remover mudança ${index + 1}`}
                            onClick={() => removeChange(index)}
                          >
                            Remover
                          </button>
                        </div>
                        <label className="form-field">
                          O quê
                          <input
                            type="text"
                            maxLength={meta.limits.max_prompt_change_chars}
                            value={change.what}
                            onChange={(e) => updateChange(index, "what", e.target.value)}
                            placeholder="O que foi alterado"
                          />
                        </label>
                        <label className="form-field">
                          Por quê
                          <input
                            type="text"
                            maxLength={meta.limits.max_prompt_change_chars}
                            value={change.why}
                            onChange={(e) => updateChange(index, "why", e.target.value)}
                            placeholder="Motivo ou evidência"
                          />
                        </label>
                        <label className="form-field">
                          Efeito esperado
                          <input
                            type="text"
                            maxLength={meta.limits.max_prompt_change_chars}
                            value={change.expected_effect}
                            onChange={(e) => updateChange(index, "expected_effect", e.target.value)}
                            placeholder="Impacto esperado na rubrica"
                          />
                        </label>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </FormShell>
          </Section>
        )}
      </div>
    </div>
  );
}
