import { useEffect, useRef, useState } from "react";
import { useGeneration } from "../hooks/useGeneration.js";
import { labelOf } from "../lib/labels.js";
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

/**
 * Aba Gerar: monta o cenário (cliente + ticket do catálogo), gera o conteúdo escolhido (ou todos) e mostra o resultado.
 * Clientes e tickets são cadastrados nas abas Cliente e Ticket; aqui só se escolhe.
 * O catálogo já chega carregado (`catalog.status === "ready"`): quem o carrega é o `App`.
 */
export default function ScenarioPage({ catalog }) {
  const { meta, profiles, tickets, versions } = catalog;
  const [profileId, setProfileId] = useState(null);
  const [ticketId, setTicketId] = useState(null);
  const [contentType, setContentType] = useState(null);
  const [promptVersion, setPromptVersion] = useState(null);
  const [useCache, setUseCache] = useState(true);
  const generation = useGeneration();
  const resultRef = useRef(null);

  // O perfil e o ticket escolhidos precisam existir: no início, ou depois de removê-los na outra aba, passa para o
  // primeiro da lista (ou fica sem escolha se a lista esvaziou).
  useEffect(() => {
    if (!profiles.some((item) => item.id === profileId)) setProfileId(profiles[0]?.id ?? null);
  }, [profiles, profileId]);

  useEffect(() => {
    if (!tickets.some((item) => item.id === ticketId)) setTicketId(tickets[0]?.id ?? null);
  }, [tickets, ticketId]);

  // O primeiro tipo de /api/meta (o diagnóstico) é o padrão do seletor.
  useEffect(() => {
    if (meta && contentType === null) setContentType(meta.content_types[0].value);
  }, [meta, contentType]);

  // A versão padrão (a que vem marcada em /api/prompt-versions) é a escolha inicial; se a escolhida sumir, volta a ela.
  useEffect(() => {
    if (versions.some((item) => item.version === promptVersion)) return;
    const fallback = versions.find((item) => item.is_default) ?? versions.at(-1);
    setPromptVersion(fallback?.version ?? null);
  }, [versions, promptVersion]);

  const profile = profiles.find((item) => item.id === profileId);
  const ticket = tickets.find((item) => item.id === ticketId);
  const ready = Boolean(profile) && Boolean(ticket);

  const handleGenerate = () => {
    generation.run({
      profile_id: profileId,
      ticket_id: ticketId,
      content_type: contentType,
      prompt_version: promptVersion,
      use_cache: useCache,
    });
  };

  // Leva o resultado para a vista (em telas estreitas ele fica abaixo do botão).
  useEffect(() => {
    if (generation.status !== "idle") resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [generation.status]);

  return (
    <>
      <div className="layout">
        <div className="stack">
          <Section step={1} title="Perfil do cliente" hint="Quem vai ler a resposta e como prefere recebê-la.">
            <ProfilePicker profiles={profiles} enums={meta.enums} value={profileId} onChange={setProfileId} />
          </Section>
          <Section step={2} title="Ticket" hint="Escolha o problema relatado pelo cliente.">
            <TicketPicker tickets={tickets} ticketId={ticketId} onTicketChange={setTicketId} />
          </Section>
        </div>
        <ScenarioSummary
          profile={profile}
          enums={meta.enums}
          ticketTitle={ticket?.title}
          contentTypes={meta.content_types}
          allOption={meta.all_option}
          contentType={contentType ?? ""}
          onContentTypeChange={setContentType}
          versions={versions}
          promptVersion={promptVersion ?? ""}
          onPromptVersionChange={setPromptVersion}
          useCache={useCache}
          onUseCacheChange={setUseCache}
          ready={ready}
          loading={generation.status === "loading"}
          onGenerate={handleGenerate}
        />
      </div>

      {generation.status !== "idle" && (
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
    </>
  );
}
