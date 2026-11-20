import { useEffect, useRef, useState } from "react";
import { useCatalog } from "../hooks/useCatalog.js";
import { useGeneration } from "../hooks/useGeneration.js";
import { labelOf } from "../lib/labels.js";
import Header from "../components/Header.jsx";
import Section from "../components/Section.jsx";
import ProfilePicker from "../components/ProfilePicker.jsx";
import TicketPicker from "../components/TicketPicker.jsx";
import ScenarioSummary from "../components/ScenarioSummary.jsx";
import DiagnosisView from "../components/DiagnosisView.jsx";
import RunInfo from "../components/RunInfo.jsx";

/** Tela principal: monta o cenário (perfil + ticket), gera o diagnóstico e mostra o resultado. */
export default function ScenarioPage() {
  const { status, meta, profiles, tickets, reload } = useCatalog();
  const [profileId, setProfileId] = useState(null);
  const [ticketId, setTicketId] = useState(null);
  const [mode, setMode] = useState("sample");
  const [freeText, setFreeText] = useState("");
  const generation = useGeneration();
  const resultRef = useRef(null);

  // Seleciona o primeiro perfil e ticket assim que o catálogo chega, para a tela nunca abrir vazia.
  useEffect(() => {
    if (profiles.length && profileId === null) setProfileId(profiles[0].id);
    if (tickets.length && ticketId === null) setTicketId(tickets[0].id);
  }, [profiles, tickets, profileId, ticketId]);

  const profile = profiles.find((item) => item.id === profileId);
  const ticket = tickets.find((item) => item.id === ticketId);
  const ticketTitle = mode === "sample" ? ticket?.title : freeText.trim() ? meta?.free_ticket_title : "";
  const ready = Boolean(profile) && (mode === "sample" ? Boolean(ticket) : freeText.trim().length > 0);

  // Ticket do catálogo ou texto livre: a API aceita exatamente um dos dois. O tipo padrão da API é o diagnóstico.
  const handleGenerate = () => {
    const source = mode === "sample" ? { ticket_id: ticketId } : { ticket_text: freeText.trim() };
    generation.run({ profile_id: profileId, ...source });
  };

  // Leva o resultado para a vista (em telas estreitas ele fica abaixo do botão).
  useEffect(() => {
    if (generation.status !== "idle") resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [generation.status]);

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
            <ScenarioSummary
              profile={profile}
              enums={meta.enums}
              ticketTitle={ticketTitle}
              ready={ready}
              loading={generation.status === "loading"}
              onGenerate={handleGenerate}
            />
          </div>
        )}

        {status === "ready" && generation.status !== "idle" && (
          <div ref={resultRef} className="result" aria-live="polite">
            <Section
              step={3}
              title={generation.result ? labelOf(meta.content_types, generation.result.run.content_type) : "Resultado"}
              hint={generation.result ? undefined : "Isso pode levar alguns segundos."}
            >
              {generation.status === "loading" && <p aria-busy="true">Gerando...</p>}
              {generation.result && (
                <div className="stack">
                  <RunInfo run={generation.result.run} savedPath={generation.result.saved_path} />
                  <DiagnosisView diagnosis={generation.result.run.output} confidenceLevels={meta.confidence_levels} />
                </div>
              )}
            </Section>
          </div>
        )}
      </main>
    </>
  );
}
