import CatalogCrud from "../components/CatalogCrud.jsx";
import ProfileBadges from "../components/ProfileBadges.jsx";
import SelectField from "../components/SelectField.jsx";
import TextField from "../components/TextField.jsx";
import { createProfile, deleteProfile, updateProfile } from "../api/client.js";
import { useCrudActions } from "../hooks/useCrudActions.js";

const API = {
  create: createProfile,
  update: updateProfile,
  remove: deleteProfile,
  created: "Cliente adicionado.",
  updated: "Cliente atualizado.",
  removed: "Cliente removido.",
};

const TEXTS = {
  listTitle: "Clientes",
  listHint: "Quem pode ser escolhido na aba Gerar.",
  empty: "Nenhum cliente. Adicione o primeiro ao lado.",
  addTitle: "Novo cliente",
  editTitle: "Editar cliente",
  addButton: "Adicionar cliente",
  editButton: "Editar cliente",
};

// Campos de escolha do cliente: a chave no perfil, o rótulo e a lista em /api/meta (`enums`).
const CHOICES = [
  { key: "tech_level", label: "Nível técnico" },
  { key: "comm_style", label: "Estilo de comunicação" },
  { key: "channel", label: "Canal" },
];

/** Aba Cliente: CRUD dos clientes (perfis), gravados em `catalog/profiles.json` (ADR 0037). */
export default function ProfilesPage({ catalog }) {
  const { meta, profiles, refreshProfiles } = catalog;
  const actions = useCrudActions(API, refreshProfiles);

  // Rascunho novo: nome vazio e a primeira opção de cada escolha, para o formulário nunca ficar sem valor válido.
  const emptyDraft = {
    id: null,
    name: "",
    ...Object.fromEntries(CHOICES.map(({ key }) => [key, meta.enums[key][0].value])),
  };

  return (
    <CatalogCrud
      id="profiles"
      texts={TEXTS}
      items={profiles}
      itemLabel={(profile) => profile.name}
      renderItem={(profile) => (
        <>
          <strong>{profile.name}</strong>
          <ProfileBadges profile={profile} enums={meta.enums} />
        </>
      )}
      emptyDraft={emptyDraft}
      toDraft={({ id, name, tech_level, comm_style, channel }) => ({ id, name, tech_level, comm_style, channel })}
      isValid={(draft) => draft.name.trim() !== ""}
      renderFields={(draft, setDraft) => (
        <>
          <TextField
            label="Nome"
            value={draft.name}
            onChange={(name) => setDraft({ ...draft, name })}
            maxLength={meta.limits.max_profile_name_chars}
            placeholder="Como o cliente é chamado"
          />
          {CHOICES.map(({ key, label }) => (
            <SelectField
              key={key}
              label={label}
              value={draft[key]}
              onChange={(value) => setDraft({ ...draft, [key]: value })}
              options={meta.enums[key]}
            />
          ))}
        </>
      )}
      actions={actions}
    />
  );
}
