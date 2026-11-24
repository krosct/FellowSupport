import { useEffect, useRef, useState } from "react";
import SelectField from "./SelectField.jsx";

// Opções do filtro de status (rótulos de interface; os valores são os do registro da execução).
const STATUS_OPTIONS = [
  { value: "ok", label: "Sucesso" },
  { value: "error", label: "Erro" },
];

// Pausa na digitação da chave de cache antes de buscar (evita uma busca por tecla).
const CACHE_KEY_DELAY_MS = 300;

/**
 * Filtros do histórico: cliente, ticket, tipo, versão, status e chave de cache (inteira ou o começo dela: lista as
 * execuções equivalentes, como o `--cache-key` da CLI). Listas vindas do catálogo e de /api/meta.
 */
export default function RunFilters({ catalog, filters, onChange, onClear }) {
  const { profiles, tickets, versions, meta } = catalog;
  const set = (key) => (value) => onChange({ ...filters, [key]: value });
  const active = Object.values(filters).some(Boolean);
  const [cacheKey, setCacheKey] = useState(filters.cache_key);
  const latest = useRef({ filters, onChange });
  latest.current = { filters, onChange };

  // "Limpar" (ou outra troca vinda de fora) também limpa o texto digitado.
  useEffect(() => setCacheKey(filters.cache_key), [filters.cache_key]);

  // Aplica a chave digitada depois da pausa, se ela mudou.
  useEffect(() => {
    const value = cacheKey.trim();
    if (value === latest.current.filters.cache_key) return undefined;
    const timer = setTimeout(() => latest.current.onChange({ ...latest.current.filters, cache_key: value }), CACHE_KEY_DELAY_MS);
    return () => clearTimeout(timer);
  }, [cacheKey]);

  return (
    <div className="filters">
      <SelectField
        label="Cliente"
        value={filters.customer_id}
        onChange={set("customer_id")}
        emptyLabel="Todos"
        options={profiles.map((item) => ({ value: item.id, label: item.name }))}
      />
      <SelectField
        label="Ticket"
        value={filters.ticket_id}
        onChange={set("ticket_id")}
        emptyLabel="Todos"
        options={tickets.map((item) => ({ value: item.id, label: item.title }))}
      />
      <SelectField
        label="Conteúdo"
        value={filters.content_type}
        onChange={set("content_type")}
        emptyLabel="Todos"
        options={meta.content_types}
      />
      <SelectField
        label="Versão"
        value={filters.prompt_version}
        onChange={set("prompt_version")}
        emptyLabel="Todas"
        options={versions.map((item) => ({ value: item.version, label: item.version }))}
      />
      <SelectField
        label="Status"
        value={filters.status}
        onChange={set("status")}
        emptyLabel="Todos"
        options={STATUS_OPTIONS}
      />
      <label className="select-field">
        <span className="summary-label">Chave de cache</span>
        <input
          type="text"
          value={cacheKey}
          onChange={(event) => setCacheKey(event.target.value)}
          placeholder="Início da chave"
          spellCheck={false}
          autoComplete="off"
        />
      </label>
      <button type="button" className="secondary outline filters-clear" disabled={!active} onClick={onClear}>
        Limpar
      </button>
    </div>
  );
}
