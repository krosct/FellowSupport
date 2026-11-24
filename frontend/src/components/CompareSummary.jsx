import Badge from "./Badge.jsx";
import ProfileBadges from "./ProfileBadges.jsx";
import SelectField from "./SelectField.jsx";
import { formatTimestamp } from "../lib/format.js";
import { labelOf } from "../lib/labels.js";

/** Rótulo de uma execução no seletor: a mais recente é a do cache (ADR 0035: toda geração ok é gravada) e vem marcada no começo, para não ser cortada. */
function runLabel(run, index) {
  const when = formatTimestamp(run.timestamp);
  return index === 0 ? `Cache · ${when}` : when;
}

/**
 * Painel lateral da aba Comparar, no mesmo molde do `ScenarioSummary` da aba Gerar: resumo do cenário, o tipo de
 * conteúdo, **um seletor por versão** (padrão "Não comparar"; as execuções vêm da mais recente, a do cache, para a
 * mais antiga) e o botão de comparar.
 */
export default function CompareSummary({
  profile,
  enums,
  ticketTitle,
  contentTypes,
  contentType,
  onContentTypeChange,
  versions,
  runsByVersion,
  choices,
  onChoiceChange,
  chosenCount,
  minVersions,
  loading,
  onCompare,
}) {
  const ready = chosenCount >= minVersions;
  return (
    <aside className="summary" aria-label="Resumo da comparação">
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
      <SelectField label="Conteúdo" value={contentType} onChange={onContentTypeChange} options={contentTypes} />
      {versions.map((version) => {
        const runs = runsByVersion[version.version] ?? [];
        return (
          <SelectField
            key={version.version}
            label={`Prompt ${version.version}${version.is_default ? " (padrão)" : ""}`}
            value={choices[version.version] ?? ""}
            onChange={(runId) => onChoiceChange(version.version, runId)}
            emptyLabel={runs.length === 0 ? "Não comparar (sem execuções)" : "Não comparar"}
            options={runs.map((run, index) => ({ value: run.run_id, label: runLabel(run, index) }))}
          />
        );
      })}
      <div className="summary-action">
        <Badge kind={ready ? "ok" : "neutral"}>
          {ready ? `${chosenCount} versões escolhidas` : `Escolha ao menos ${minVersions} versões`}
        </Badge>
        <button type="button" disabled={!ready || loading} aria-busy={loading} onClick={onCompare}>
          {loading ? "Comparando..." : "Comparar"}
        </button>
      </div>
    </aside>
  );
}
