import Badge from "./Badge.jsx";
import ProfileBadges from "./ProfileBadges.jsx";

/** Resumo do cenário escolhido (perfil + ticket) e o botão de gerar, ativado na Etapa 1. */
export default function ScenarioSummary({ profile, enums, ticketTitle, ready }) {
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
      <div className="summary-action">
        <Badge kind={ready ? "ok" : "neutral"}>{ready ? "Cenário completo" : "Cenário incompleto"}</Badge>
        <button type="button" disabled>
          Gerar conteúdo
        </button>
        <small className="hint">Disponível na próxima etapa.</small>
      </div>
    </aside>
  );
}
