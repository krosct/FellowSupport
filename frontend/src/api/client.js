// Único ponto de acesso HTTP do front-end. Nenhum outro arquivo deve chamar `fetch`.

/** Erro de API com a mensagem já pronta para exibir ao usuário (ex.: no toast). */
export class ApiError extends Error {
  constructor(message, status, conflicts = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    // Só no 409 de substituição de cache: todas as entradas que o pedido trocaria (ADR 0036).
    this.conflicts = conflicts;
  }
}

/** O erro é o 409 "substituiria entradas do cache"? O pedido deve ser repetido com `confirm_replace: true`. */
export const isCacheReplaceConflict = (error) =>
  error instanceof ApiError && error.status === 409 && Array.isArray(error.conflicts);

/** Faz a requisição e devolve a resposta já conferida; converte falhas de rede e de HTTP em ApiError. */
async function send(path, options = {}) {
  let response;
  try {
    const { headers, ...rest } = options;
    response = await fetch(path, { headers: { Accept: "application/json", ...headers }, ...rest });
  } catch {
    throw new ApiError("Não foi possível falar com o servidor.", 0);
  }
  if (!response.ok) {
    // A API devolve {"detail": "..."}; o proxy ou o servidor podem devolver texto puro.
    let detail = `Erro ${response.status} ao chamar ${path}.`;
    let conflicts = null;
    try {
      const body = await response.json();
      if (Array.isArray(body.conflicts)) conflicts = body.conflicts;
      if (typeof body.detail === "string") detail = body.detail;
      // Erros de formato do corpo (FastAPI) vêm como lista de `{loc, msg}`: junta em uma frase.
      else if (Array.isArray(body.detail)) detail = body.detail.map((item) => `${item.loc?.slice(1).join(".")}: ${item.msg}`).join("; ");
    } catch {
      /* corpo não é JSON: mantém a mensagem padrão */
    }
    throw new ApiError(detail, response.status, conflicts);
  }
  return response;
}

/** Faz a requisição e devolve o JSON. */
const request = async (path, options) => (await send(path, options)).json();

// Cabeçalho com o total das listagens paginadas (o mesmo de `TOTAL_COUNT_HEADER` na API).
const TOTAL_COUNT_HEADER = "X-Total-Count";

/** Listagem paginada: `{ items, total }`, com o total de todas as páginas vindo do cabeçalho da API. */
async function requestPage(path) {
  const response = await send(path);
  return { items: await response.json(), total: Number(response.headers.get(TOTAL_COUNT_HEADER) ?? 0) };
}

/** `?chave=valor` só com os valores preenchidos (vazios e nulos são ignorados). */
function queryString(params) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== "" && value != null) query.set(key, value);
  });
  const text = query.toString();
  return text ? `?${text}` : "";
}

const SESSION_KEYS_STORAGE = "fellowsupport.sessionKeys";
const EMPTY_SESSION_KEYS = { openrouter_api_key: "", admin_api_key: "" };
let memorySessionKeys = { ...EMPTY_SESSION_KEYS };

/** Lê as chaves da sessão atual (sessionStorage com fallback em memória). */
export function getSessionKeys() {
  try {
    const raw = window.sessionStorage.getItem(SESSION_KEYS_STORAGE);
    if (!raw) return { ...memorySessionKeys };
    const parsed = JSON.parse(raw);
    return {
      openrouter_api_key: typeof parsed.openrouter_api_key === "string" ? parsed.openrouter_api_key : "",
      admin_api_key: typeof parsed.admin_api_key === "string" ? parsed.admin_api_key : "",
    };
  } catch {
    return { ...memorySessionKeys };
  }
}

/** Grava as chaves apenas para a sessão atual do navegador. */
export function setSessionKeys(keys) {
  const next = {
    openrouter_api_key: (keys?.openrouter_api_key ?? "").trim(),
    admin_api_key: (keys?.admin_api_key ?? "").trim(),
  };
  memorySessionKeys = next;
  try {
    window.sessionStorage.setItem(SESSION_KEYS_STORAGE, JSON.stringify(next));
  } catch {
    /* sessionStorage indisponível: mantém em memória */
  }
  return next;
}

/** Cabeçalhos e corpo de uma requisição com JSON. */
const jsonRequest = (method, payload, headers = {}) => ({
  method,
  headers: { "Content-Type": "application/json", ...headers },
  body: JSON.stringify(payload),
});

const adminHeaders = () => {
  const { admin_api_key } = getSessionKeys();
  return admin_api_key ? { "X-Admin-Key": admin_api_key } : {};
};

const openrouterHeaders = () => {
  const { openrouter_api_key } = getSessionKeys();
  return openrouter_api_key ? { "X-OpenRouter-Key": openrouter_api_key } : {};
};

/** Constantes do domínio (enums, tipos de conteúdo, rubrica, versão padrão). */
export const getMeta = () => request("/api/meta");
/** Clientes (perfis) do catálogo. */
export const getProfiles = () => request("/api/profiles");
/** Tickets do catálogo. */
export const getTickets = () => request("/api/tickets");

/** Cria um cliente no catálogo. `payload`: `{ name, tech_level, comm_style, channel }`. Devolve o perfil com o id gerado. */
export const createProfile = (payload) => request("/api/profiles", jsonRequest("POST", payload, adminHeaders()));
/** Troca os dados de um cliente (o id não muda). Devolve o perfil. */
export const updateProfile = (profileId, payload) =>
  request(`/api/profiles/${encodeURIComponent(profileId)}`, jsonRequest("PUT", payload, adminHeaders()));
/** Remove um cliente do catálogo e devolve o que foi removido. */
export const deleteProfile = (profileId) =>
  request(`/api/profiles/${encodeURIComponent(profileId)}`, { method: "DELETE", headers: adminHeaders() });

/** Cria um ticket no catálogo. `payload`: `{ title, text }`. Devolve o ticket com o id gerado pelo servidor. */
export const createTicket = (payload) => request("/api/tickets", jsonRequest("POST", payload, adminHeaders()));
/** Troca título e corpo de um ticket (o id não muda). `payload`: `{ title, text }`. Devolve o ticket. */
export const updateTicket = (ticketId, payload) =>
  request(`/api/tickets/${encodeURIComponent(ticketId)}`, jsonRequest("PUT", payload, adminHeaders()));
/** Remove um ticket do catálogo e devolve o que foi removido. */
export const deleteTicket = (ticketId) =>
  request(`/api/tickets/${encodeURIComponent(ticketId)}`, { method: "DELETE", headers: adminHeaders() });

/** Versões de prompt disponíveis (conteúdo do meta.json e marca de versão padrão). */
export const getPromptVersions = () => request("/api/prompt-versions");
/** Detalhe de uma versão de prompt (metadados e mapa de arquivos). */
export const getPrompt = (version) => request(`/api/prompts/${encodeURIComponent(version)}`);
/** Cria uma versão de prompt derivada de `based_on`. Devolve os detalhes com o hash calculado. */
export const createPrompt = (payload) => request("/api/prompts", jsonRequest("POST", payload, adminHeaders()));
/** Remove uma versão de prompt (v1 não pode ser removida). */
export const deletePrompt = (version) =>
  request(`/api/prompts/${encodeURIComponent(version)}`, { method: "DELETE", headers: adminHeaders() });

/**
 * Gera um conteúdo. `payload`: `{ profile_id, ticket_id, content_type?, prompt_version?, use_cache?, confirm_replace? }`.
 * Devolve `{ saved_path, run }` (um tipo) ou `{ results, warning }` ("Todos"; `warning` lista os tipos que falharam).
 * O tipo padrão da API é o diagnóstico. `use_cache` (padrão `true` na API) liga o cache.
 */
export const generate = (payload) => request("/api/generate", jsonRequest("POST", payload, openrouterHeaders()));

/**
 * Uma página do histórico de execuções, da mais recente para a mais antiga: `{ items, total }`. `filters` aceita
 * `customer_id`, `ticket_id`, `content_type`, `prompt_version`, `status`, `cache_key`, `limit` e `offset`; valores
 * vazios são ignorados.
 */
export const getRuns = (filters = {}) => requestPage(`/api/runs${queryString(filters)}`);

/** Detalhe de uma execução: `{ saved_path, run }`, a mesma forma da resposta de `generate`. */
export const getRun = (runId) => request(`/api/runs/${encodeURIComponent(runId)}`);

/**
 * Salva a comparação. `payload`: `{ run_ids, evaluations: { [run_id]: { [critério]: { score, justification } } },
 * conclusion? }`. Devolve `{ saved_path, comparison }`.
 */
export const saveComparison = (payload) => request("/api/comparisons", jsonRequest("POST", payload));

/** Uma página das comparações salvas, da mais recente para a mais antiga (resumos): `{ items, total }`. */
export const getComparisons = ({ limit, offset } = {}) => requestPage(`/api/comparisons${queryString({ limit, offset })}`);

/**
 * Cache das comparações (ADR 0038): a comparação mais recente já salva dessas execuções, `{ saved_path, comparison }`, ou
 * `null` se não houver. Só lê os arquivos salvos; não gera nada.
 */
export const lookupComparison = (runIds) => {
  const query = new URLSearchParams();
  runIds.forEach((runId) => query.append("run_ids", runId));
  return request(`/api/comparisons/lookup?${query}`);
};

/** Comparação completa: `{ saved_path, comparison }`. */
export const getComparison = (comparisonId) => request(`/api/comparisons/${encodeURIComponent(comparisonId)}`);
