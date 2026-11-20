import { useEffect, useRef, useState } from "react";
import { useCatalog } from "../hooks/useCatalog.js";
import { useGeneration } from "../hooks/useGeneration.js";
import { labelOf } from "../lib/labels.js";
import Header from "../components/Header.jsx";
import Section from "../components/Section.jsx";
import ProfilePicker from "../components/ProfilePicker.jsx";
import TicketPicker from "../components/TicketPicker.jsx";
import ScenarioSummary from "../components/ScenarioSummary.jsx";
import GenerationResults from "../components/GenerationResults.jsx";

/** Título do resultado: o rótulo do tipo gerado, ou o de "Todos" quando vieram vários. */
function resultTitle(items, meta) {
  if (items.length === 0) return "Resultado";
  return items.length > 1 ? meta.all_option.label : labelOf(meta.content_types, items[0].content_type);
}

/** Tela principal: monta o cenário (perfil + ticket), gera o conteúdo escolhido (ou todos) e mostra o resultado. */
export default function ScenarioPage() {
  const { status, meta, profiles, tickets, reload } = useCatalog();
  const [profileId, setProfileId] = useState(null);
  const [ticketId, setTicketId] = useState(null);
  const [mode, setMode] = useState("sample");
  const [freeText, setFreeText] = useState("");
  const [contentType, setContentType] = useState(null);
  const generation = useGeneration();
  const resultRef = useRef(null);

  // Seleciona o primeiro perfil e ticket assim que o catálogo chega, para a tela nunca abrir vazia.
  useEffect(() => {
    if (profiles.length && profileId === null) setProfileId(profiles[0].id);
    if (tickets.length && ticketId === null) setTicketId(tickets[0].id);
  }, [profiles, tickets, profileId, ticketId]);

  // O primeiro tipo de /api/meta (o diagnóstico) é o padrão do seletor.
  useEffect(() => {
    if (meta && contentType === null) setContentType(meta.content_types[0].value);
  }, [meta, contentType]);

  const profile = profiles.find((item) => item.id === profileId);
  const ticket = tickets.find((item) => item.id === ticketId);
  const ticketTitle = mode === "sample" ? ticket?.title : freeText.trim() ? meta?.free_ticket_title : "";
  const ready = Boolean(profile) && (mode === "sample" ? Boolean(ticket) : freeText.trim().length > 0);

  // Ticket do catálogo ou texto livre: a API aceita exatamente um dos dois.
  const handleGenerate = () => {
    const source = mode === "sample" ? { ticket_id: ticketId } : { ticket_text: freeText.trim() };
    generation.run({ profile_id: profileId, content_type: contentType, ...source });
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
              contentTypes={meta.content_types}
              allOption={meta.all_option}
              contentType={contentType ?? ""}
              onContentTypeChange={setContentType}
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
              title={resultTitle(generation.items, meta)}
              hint={generation.status === "loading" ? "Isso pode levar alguns segundos." : undefined}
            >
              {generation.status === "loading" && <p aria-busy="true">Gerando...</p>}
              {generation.items.length > 0 && <GenerationResults items={generation.items} meta={meta} />}
            </Section>
          </div>
        )}
      </main>
    </>
  );
}
