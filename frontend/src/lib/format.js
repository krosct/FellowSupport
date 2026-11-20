// Formatadores de exibição. Texto de interface curto; nada de regra de negócio aqui.

/** Latência em milissegundos como "950 ms" ou "1,8 s". */
export function formatLatency(ms) {
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} s`;
}

/** Primeiros caracteres de um hash, para exibição. */
export const shortHash = (hash, size = 8) => (hash ? hash.slice(0, size) : "");
