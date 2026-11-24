import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getRun, lookupComparison, saveComparison } from "../api/client.js";
import { useRuns } from "../hooks/useRuns.js";
import { emptyEvaluation, evaluationPayload, isEvaluationComplete } from "../lib/rubric.js";
import ConfirmDialog from "../components/ConfirmDialog.jsx";
import Section from "../components/Section.jsx";
import ProfilePicker from "../components/ProfilePicker.jsx";
import TicketPicker from "../components/TicketPicker.jsx";
import CompareSummary from "../components/CompareSummary.jsx";
import VersionChanges from "../components/VersionChanges.jsx";
import SavedComparison from "../components/SavedComparison.jsx";
import CompareColumn from "../components/CompareColumn.jsx";
import VersionCarousel from "../components/VersionCarousel.jsx";
import ComparisonVerdict from "../components/ComparisonVerdict.jsx";
import { useToast } from "../components/Toast.jsx";

/** Dica do resultado: comparação salva (só leitura) ou avaliação nova. */
function resultHint(result, loading) {
  if (loading) return "Isso pode levar alguns segundos.";
  if (result.kind === "cached") return "Comparação já salva dessas execuções, com as notas dadas antes.";
  return "Dê as três notas em cada lado e salve a comparação.";
}

const SAVED_CHOICE = { load: "load", again: "again" }; // respostas da janela "Já existe uma comparação"

const RUN_LIMIT = 500; // teto do filtro `limit` de GET /api/runs

/**
 * Aba Comparar, no mesmo molde da aba Gerar: à esquerda o perfil e o ticket, à direita o painel com o tipo de conteúdo
 * e **um seletor por versão** (padrão "Não comparar"), cujas opções são as execuções já feitas daquela versão no
 * cenário, da mais recente (a do cache) para a mais antiga. Embaixo ficam "o que mudou" entre as versões e a comparação.
 * Ao comparar, procura em `var/comparisons/` (pela API, ADR 0038) uma comparação já salva dessas mesmas execuções; nenhuma
 * execução é gerada aqui. Sem ela, abre a avaliação nova. Com ela, uma janela deixa escolher entre **Carregar comparação**
 * (mostra as notas dadas antes, só leitura) e **Comparar novamente** (avaliação zerada; a salva não é tocada). A justiça do
 * cenário vale na gravação (ADR 0021).
 */
export default function ComparePage({ catalog, active }) {
  const { meta, profiles, tickets, versions } = catalog;
  const toast = useToast();
  const [profileId, setProfileId] = useState(null);
  const [ticketId, setTicketId] = useState(null);
  const [contentType, setContentType] = useState(null);
  const [choices, setChoices] = useState({}); // versão -> run_id escolhido ("" = Não comparar)
  const [result, setResult] = useState({ status: "idle", kind: "fresh", runs: [] });
  // Estado por execução (chave: run_id): notas do candidato. Zera a cada nova comparação.
  const [forms, setForms] = useState({});
  const [conclusion, setConclusion] = useState("");
  const [saving, setSaving] = useState(false);
  const [runsKey, setRunsKey] = useState(0); // muda a cada avaliação nova: remonta o carrossel e zera notas e conclusão
  const [savedAsk, setSavedAsk] = useState(null); // `{ resolve }` enquanto a janela "Já existe uma comparação" está aberta
  const latestResult = useRef(result); // o resultado na tela, para restaurá-lo se a janela for cancelada
  latestResult.current = result;
  const [saved, setSaved] = useState(null);
  const resultRef = useRef(null);

  useEffect(() => {
    if (!profiles.some((item) => item.id === profileId)) setProfileId(profiles[0]?.id ?? null);
  }, [profiles, profileId]);
  useEffect(() => {
    if (!tickets.some((item) => item.id === ticketId)) setTicketId(tickets[0]?.id ?? null);
  }, [tickets, ticketId]);
  useEffect(() => {
    if (meta && contentType === null) setContentType(meta.content_types[0].value);
  }, [meta, contentType]);

  // Trocar o cenário invalida as execuções escolhidas e o resultado na tela.
  useEffect(() => {
    setChoices({});
    setResult({ status: "idle", kind: "fresh", runs: [] });
  }, [profileId, ticketId, contentType]);

  // Execuções do cenário (só as geradas de fato, sem os acertos de cache), recarregadas ao abrir a aba.
  const filters = useMemo(
    () => ({ customer_id: profileId, ticket_id: ticketId, content_type: contentType, status: "ok", limit: RUN_LIMIT }),
    [profileId, ticketId, contentType],
  );
  const history = useRuns(filters, active && Boolean(profileId && ticketId && contentType));
  const runsByVersion = useMemo(() => {
    const grouped = {};
    for (const run of history.runs) {
      if (run.cache_hit) continue;
      (grouped[run.prompt_version] ??= []).push(run);
    }
    return grouped; // a API já devolve da mais recente para a mais antiga
  }, [history.runs]);

  const profile = profiles.find((item) => item.id === profileId);
  const ticket = tickets.find((item) => item.id === ticketId);
  const chosenVersions = versions.filter((version) => choices[version.version]);
  const minVersions = meta.limits.min_compared_versions;
  const loading = result.status === "loading";
  const { runs } = result;

  const setChoice = (version, runId) => setChoices((current) => ({ ...current, [version]: runId }));

  // Pergunta o que fazer com a comparação já salva; resolve `load`, `again` ou `null` (Esc ou clique fora).
  const askSavedChoice = useCallback(
    () => new Promise((resolve) => setSavedAsk({ resolve })),
    [],
  );
  const answerSaved = (choice) => {
    savedAsk?.resolve(choice);
    setSavedAsk(null);
  };

  // Reúne as execuções escolhidas e procura uma comparação já salva delas; sem ela abre a avaliação nova.
  const handleCompare = useCallback(async () => {
    const previous = latestResult.current;
    setResult({ status: "loading", kind: "fresh", runs: [] });
    try {
      const items = await Promise.all(
        chosenVersions.map(async (version) => {
          const response = await getRun(choices[version.version]);
          return { prompt_version: version.version, saved_path: response.saved_path, run: response.run };
        }),
      );
      const found = await lookupComparison(items.map((item) => item.run.run_id));
      const choice = found ? await askSavedChoice() : SAVED_CHOICE.again;
      if (choice === null) {
        setResult(previous.status === "loading" ? { status: "idle", kind: "fresh", runs: [] } : previous);
        return;
      }
      setForms({});
      setConclusion("");
      setSaved(null);
      setRunsKey((key) => key + 1);
      setResult(
        choice === SAVED_CHOICE.load
          ? { status: "done", kind: "cached", runs: [], saved: found }
          : { status: "done", kind: "fresh", runs: items },
      );
      requestAnimationFrame(() => resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
    } catch (error) {
      toast.error(error.message);
      setResult({ status: "idle", kind: "fresh", runs: [] });
    }
  }, [chosenVersions, choices, askSavedChoice, toast]);

  const formOf = (runId) => forms[runId] ?? emptyEvaluation(meta.rubric);
  const updateForm = (runId, update) =>
    setForms((current) => ({ ...current, [runId]: update(current[runId] ?? emptyEvaluation(meta.rubric)) }));
  const complete = runs.length > 0 && runs.every(({ run }) => isEvaluationComplete(meta.rubric, formOf(run.run_id)));

  const handleSave = async () => {
    setSaving(true);
    try {
      const response = await saveComparison({
        run_ids: runs.map(({ run }) => run.run_id),
        evaluations: Object.fromEntries(
          runs.map(({ run }) => [run.run_id, evaluationPayload(meta.rubric, formOf(run.run_id))]),
        ),
        conclusion: conclusion.trim() || null,
      });
      setSaved(response);
      toast.info("Comparação salva.");
    } catch (error) {
      toast.error(error.message);
    } finally {
      setSaving(false);
    }
  };

  const hasChanges = chosenVersions.some((version) => version.based_on);

  return (
    <>
      <div className="layout">
        <div className="stack">
          <Section step={1} id="cmp-profile" title="Perfil do cliente" hint="Quem vai ler a resposta e como prefere recebê-la.">
            <ProfilePicker profiles={profiles} enums={meta.enums} value={profileId} onChange={setProfileId} />
          </Section>
          <Section step={2} id="cmp-ticket" title="Ticket" hint="Escolha o problema relatado pelo cliente.">
            <TicketPicker tickets={tickets} ticketId={ticketId} onTicketChange={setTicketId} />
          </Section>
        </div>
        <CompareSummary
          profile={profile}
          enums={meta.enums}
          ticketTitle={ticket?.title}
          contentTypes={meta.content_types}
          contentType={contentType ?? ""}
          onContentTypeChange={setContentType}
          versions={versions}
          runsByVersion={runsByVersion}
          choices={choices}
          onChoiceChange={setChoice}
          chosenCount={chosenVersions.length}
          minVersions={minVersions}
          loading={loading}
          onCompare={handleCompare}
        />
      </div>

      <ConfirmDialog
        open={savedAsk !== null}
        title="Já existe uma comparação"
        confirmLabel="Carregar comparação"
        declineLabel="Comparar novamente"
        onConfirm={() => answerSaved(SAVED_CHOICE.load)}
        onDecline={() => answerSaved(SAVED_CHOICE.again)}
        onCancel={() => answerSaved(null)}
      >
        <p>Estas execuções já foram comparadas. Carregar mostra as notas dadas antes; comparar novamente abre uma avaliação zerada e mantém a anterior.</p>
      </ConfirmDialog>

      {hasChanges && (
        <div className="result">
          <Section step={3} id="cmp-changes" title="O que mudou" hint="Diferenças entre as versões escolhidas.">
            <VersionChanges versions={chosenVersions} />
          </Section>
        </div>
      )}

      {result.status !== "idle" && (
        <div ref={resultRef} className="result" aria-live="polite">
          <Section
            step={hasChanges ? 4 : 3}
            id="cmp-result"
            title="Saídas e avaliação"
            hint={resultHint(result, loading)}
          >
            {loading && <p aria-busy="true">Reunindo as versões...</p>}
            {result.kind === "cached" && result.saved && <SavedComparison data={result.saved} meta={meta} />}
            {result.kind === "fresh" && runs.length > 0 && (
              <div className="stack">
                <VersionCarousel
                  key={runsKey}
                  label="Versões comparadas"
                  items={runs}
                  getKey={(item) => item.run.run_id}
                  getLabel={(item) => item.prompt_version}
                  render={(item) => (
                    <CompareColumn
                      item={item}
                      meta={meta}
                      form={formOf(item.run.run_id)}
                      onFormChange={(update) => updateForm(item.run.run_id, update)}
                    />
                  )}
                />
                <label className="compare-conclusion">
                  <span className="summary-label">Conclusão (opcional)</span>
                  <textarea
                    rows={2}
                    maxLength={meta.limits.conclusion_max_chars}
                    placeholder="Qual versão serviu melhor e por quê?"
                    value={conclusion}
                    onChange={(event) => setConclusion(event.target.value)}
                  />
                </label>
                <div className="compare-actions">
                  <span className="hint compare-status" data-complete={complete}>
                    {complete ? "Avaliação completa." : "Faltam notas ou justificativas."}
                  </span>
                  <button type="button" disabled={!complete || saving} aria-busy={saving} onClick={handleSave}>
                    {saving ? "Salvando..." : "Salvar comparação"}
                  </button>
                </div>
                {saved && <ComparisonVerdict comparison={saved.comparison} savedPath={saved.saved_path} rubric={meta.rubric} />}
              </div>
            )}
          </Section>
        </div>
      )}
    </>
  );
}
