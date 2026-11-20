// Único ponto de acesso HTTP do front-end. Nenhum outro arquivo deve chamar `fetch`.

/** Erro de API com a mensagem já pronta para exibir ao usuário (ex.: no toast). */
export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** Faz a requisição e devolve o JSON; converte falhas de rede e de HTTP em ApiError. */
async function request(path, options = {}) {
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
    try {
      const body = await response.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* corpo não é JSON: mantém a mensagem padrão */
    }
    throw new ApiError(detail, response.status);
  }
  return response.json();
}

/** Constantes do domínio (enums, tipos de conteúdo, rubrica, versão padrão). */
export const getMeta = () => request("/api/meta");
/** Perfis de cliente do catálogo. */
export const getProfiles = () => request("/api/profiles");
/** Tickets de exemplo do catálogo. */
export const getTickets = () => request("/api/tickets");
/** Versões de prompt disponíveis (conteúdo do meta.json e marca de versão padrão). */
export const getPromptVersions = () => request("/api/prompt-versions");

/**
 * Gera um conteúdo. `payload`: `{ profile_id, ticket_id | ticket_text, content_type?, prompt_version? }`.
 * Devolve `{ saved_path, run }`; o tipo padrão da API é o diagnóstico.
 */
export const generate = (payload) =>
  request("/api/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
