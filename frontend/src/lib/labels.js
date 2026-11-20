// Tradução de valores de enum para rótulos. Os rótulos vêm de /api/meta; nada é repetido aqui.

/** Devolve o rótulo de `value` dentro de uma lista `[{value, label}]` (ou o próprio valor se não achar). */
export function labelOf(options, value) {
  return options?.find((option) => option.value === value)?.label ?? value;
}
