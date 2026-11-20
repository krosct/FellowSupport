// Formatadores de exibição. Texto de interface curto; nada de regra de negócio aqui.

/** Latência em milissegundos como "950 ms" ou "1,8 s". */
export function formatLatency(ms) {
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} s`;
}

/** Primeiros caracteres de um hash, para exibição. */
export const shortHash = (hash, size = 8) => (hash ? hash.slice(0, size) : "");

/**
 * `2026-11-20T14:03:11-03:00` como `20/11/2026 14:03:11`. O registro já está no fuso de APP_TIMEZONE (Brasília por
 * padrão): o texto é reordenado sem converter para o fuso do navegador.
 */
export function formatTimestamp(timestamp) {
  const [date = "", time = ""] = timestamp.slice(0, 19).split("T");
  const [year, month, day] = date.split("-");
  return `${day}/${month}/${year} ${time}`;
}
