// Rotas por hash (ADR 0013, sem react-router). `#/gerar`, `#/historico` e `#/historico/<id>`.
// As abas são definidas aqui uma vez; o resto do app só consulta.

/** Abas do app: `value` é o identificador interno e `path` o trecho do hash. */
export const TABS = [
  { value: "generate", label: "Gerar", path: "gerar" },
  { value: "history", label: "Histórico", path: "historico" },
];

/** Aba aberta quando o hash está vazio ou desconhecido. */
export const DEFAULT_TAB = TABS[0].value;

/** Lê um hash (`location.hash`) e devolve `{ tab, runId }`; `runId` só existe na aba Histórico. */
export function parseHash(hash) {
  const [path, id] = hash.replace(/^#\/?/, "").split("/");
  const tab = TABS.find((item) => item.path === path)?.value ?? DEFAULT_TAB;
  return { tab, runId: tab === "history" && id ? decodeURIComponent(id) : null };
}

/** Monta o hash de uma aba (e, no Histórico, de uma execução). */
export function hashFor(tab, runId) {
  const path = TABS.find((item) => item.value === tab)?.path ?? TABS[0].path;
  return runId ? `#/${path}/${encodeURIComponent(runId)}` : `#/${path}`;
}
