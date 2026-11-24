import Badge from "./Badge.jsx";
import CacheCheckbox from "./CacheCheckbox.jsx";
import ContentTypePicker from "./ContentTypePicker.jsx";
import ProfileBadges from "./ProfileBadges.jsx";
import SelectField from "./SelectField.jsx";

/**
 * Resumo do cenário escolhido (perfil + ticket), os seletores do tipo de conteúdo e da versão do prompt, a opção "Usar cache" e o botão de
 * gerar.
 */
export default function ScenarioSummary({
  profile,
  enums,
  ticketTitle,
  contentTypes,
  allOption,
  contentType,
  onContentTypeChange,
  versions,
  promptVersion,
  onPromptVersionChange,
  useCache,
  onUseCacheChange,
  ready,
  loading,
  onGenerate,
}) {
  return (
    <aside className="summary" aria-label="Resumo do cenário">
      <div>
        <p className="summary-label">Cliente</p>
        {profile ? (
          <>
            <strong>{profile.name}</strong>
            <ProfileBadges profile={profile} enums={enums} />
          </>
        ) : (
          <Badge>Nenhum perfil</Badge>
        )}
      </div>
      <div>
        <p className="summary-label">Ticket</p>
        <strong>{ticketTitle || "Nenhum ticket"}</strong>
      </div>
      <ContentTypePicker types={contentTypes} allOption={allOption} value={contentType} onChange={onContentTypeChange} />
      <SelectField
        label="Versão do prompt"
        value={promptVersion}
        onChange={onPromptVersionChange}
        options={versions.map((item) => ({
          value: item.version,
          label: item.is_default ? `${item.version} (padrão)` : item.version,
        }))}
      />
      <CacheCheckbox checked={useCache} onChange={onUseCacheChange} />
      <div className="summary-action">
        <Badge kind={ready ? "ok" : "neutral"}>{ready ? "Cenário completo" : "Cenário incompleto"}</Badge>
        <button type="button" disabled={!ready || loading} aria-busy={loading} onClick={onGenerate}>
          {loading ? "Gerando..." : "Gerar"}
        </button>
      </div>
    </aside>
  );
}
