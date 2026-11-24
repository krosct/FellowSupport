// Rotas por hash (ADR 0013, sem react-router): `#/cliente`, `#/ticket`, `#/prompt`, `#/gerar`, `#/comparar`, `#/historico`, `#/historico/<id da execução>`,
// `#/historico/comparacoes` e `#/historico/comparacoes/<id da comparação>`.
// As abas são definidas aqui uma vez; o resto do app só consulta.

/** Abas do app: `value` é o identificador interno e `path` o trecho do hash. */
export const TABS = [
  { value: "clients", label: "Cliente", path: "cliente" },
  { value: "tickets", label: "Ticket", path: "ticket" },
  { value: "prompts", label: "Prompt", path: "prompt" },
  { value: "generate", label: "Gerar", path: "gerar" },
  { value: "compare", label: "Comparar", path: "comparar" },
  { value: "history", label: "Histórico", path: "historico" },
];

/** Aba aberta quando o hash está vazio ou desconhecido. */
export const DEFAULT_TAB = "generate";

/** Trecho do hash que separa as comparações das execuções dentro do Histórico. */
const COMPARISONS_PATH = "comparacoes";

/**
 * Lê um hash (`location.hash`) e devolve `{ tab, view, runId, comparisonId }`. `view` (`"runs"` ou `"comparisons"`) e os
 * ids só existem na aba Histórico: `runId` abre uma execução e `comparisonId` abre uma comparação.
 */
export function parseHash(hash) {
  const [path, second, third] = hash.replace(/^#\/?/, "").split("/");
  const tab = TABS.find((item) => item.path === path)?.value ?? DEFAULT_TAB;
  if (tab !== "history") return { tab, view: "runs", runId: null, comparisonId: null };
  if (second === COMPARISONS_PATH) {
    return { tab, view: "comparisons", runId: null, comparisonId: third ? decodeURIComponent(third) : null };
  }
  return { tab, view: "runs", runId: second ? decodeURIComponent(second) : null, comparisonId: null };
}

/** Monta o hash de uma aba (e, no Histórico, de uma execução). */
export function hashFor(tab, runId) {
  const path = TABS.find((item) => item.value === tab)?.path ?? TABS.find((item) => item.value === DEFAULT_TAB).path;
  return runId ? `#/${path}/${encodeURIComponent(runId)}` : `#/${path}`;
}

/** Hash da lista de comparações do Histórico (ou de uma comparação, com `comparisonId`). */
export function comparisonsHash(comparisonId) {
  const base = `${hashFor("history")}/${COMPARISONS_PATH}`;
  return comparisonId ? `${base}/${encodeURIComponent(comparisonId)}` : base;
}
