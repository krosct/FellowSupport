import Badge from "./Badge.jsx";
import CheckboxField from "./CheckboxField.jsx";
import ContentTypePicker from "./ContentTypePicker.jsx";
import ProfileBadges from "./ProfileBadges.jsx";

/**
 * Resumo do cenário escolhido (perfil + ticket), o seletor do tipo de conteúdo, a opção "Usar cache" e o botão de
 * gerar. `cacheAvailable` é falso quando o servidor desligou o cache (CACHE_ENABLED=false).
 */
export default function ScenarioSummary({
  profile,
  enums,
  ticketTitle,
  contentTypes,
  allOption,
  contentType,
  onContentTypeChange,
  useCache,
  onUseCacheChange,
  cacheAvailable,
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
      <CheckboxField
        label="Usar cache"
        hint={cacheAvailable ? undefined : "Desligado no servidor"}
        checked={cacheAvailable && useCache}
        onChange={onUseCacheChange}
        disabled={!cacheAvailable}
      />
      <div className="summary-action">
        <Badge kind={ready ? "ok" : "neutral"}>{ready ? "Cenário completo" : "Cenário incompleto"}</Badge>
        <button type="button" disabled={!ready || loading} aria-busy={loading} onClick={onGenerate}>
          {loading ? "Gerando..." : "Gerar"}
        </button>
      </div>
    </aside>
  );
}
