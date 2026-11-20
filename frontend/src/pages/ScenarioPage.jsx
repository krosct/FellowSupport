import { useEffect, useState } from "react";
import { useCatalog } from "../hooks/useCatalog.js";
import Header from "../components/Header.jsx";
import Section from "../components/Section.jsx";
import ProfilePicker from "../components/ProfilePicker.jsx";
import TicketPicker from "../components/TicketPicker.jsx";
import ScenarioSummary from "../components/ScenarioSummary.jsx";

/** Tela inicial: monta o cenário (perfil + ticket). A geração de conteúdo entra na Etapa 1. */
export default function ScenarioPage() {
  const { status, meta, profiles, tickets, reload } = useCatalog();
  const [profileId, setProfileId] = useState(null);
  const [ticketId, setTicketId] = useState(null);
  const [mode, setMode] = useState("sample");
  const [freeText, setFreeText] = useState("");

  // Seleciona o primeiro perfil e ticket assim que o catálogo chega, para a tela nunca abrir vazia.
  useEffect(() => {
    if (profiles.length && profileId === null) setProfileId(profiles[0].id);
    if (tickets.length && ticketId === null) setTicketId(tickets[0].id);
  }, [profiles, tickets, profileId, ticketId]);

  const profile = profiles.find((item) => item.id === profileId);
  const ticket = tickets.find((item) => item.id === ticketId);
  const ticketTitle = mode === "sample" ? ticket?.title : freeText.trim() ? "Ticket digitado" : "";
  const ready = Boolean(profile) && (mode === "sample" ? Boolean(ticket) : freeText.trim().length > 0);

  return (
    <>
      <Header llm={meta?.llm} />
      <main className="container">
        {status === "loading" && <p aria-busy="true">Carregando catálogo...</p>}

        {status === "error" && (
          <div className="panel error-panel" role="alert">
            <p>Não foi possível carregar o catálogo.</p>
            <button type="button" onClick={reload}>
              Tentar novamente
            </button>
          </div>
        )}

        {status === "ready" && (
          <div className="layout">
            <div className="stack">
              <Section step={1} title="Perfil do cliente" hint="Quem vai ler a resposta e como prefere recebê-la.">
                <ProfilePicker profiles={profiles} enums={meta.enums} value={profileId} onChange={setProfileId} />
              </Section>
              <Section step={2} title="Ticket" hint="Escolha um exemplo ou digite o seu.">
                <TicketPicker
                  tickets={tickets}
                  mode={mode}
                  onModeChange={setMode}
                  ticketId={ticketId}
                  onTicketChange={setTicketId}
                  freeText={freeText}
                  onFreeTextChange={setFreeText}
                  maxChars={meta.limits.max_ticket_chars}
                />
              </Section>
            </div>
            <ScenarioSummary profile={profile} enums={meta.enums} ticketTitle={ticketTitle} ready={ready} />
          </div>
        )}
      </main>
    </>
  );
}
