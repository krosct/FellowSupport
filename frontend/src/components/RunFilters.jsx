import SelectField from "./SelectField.jsx";

// Opções do filtro de status (rótulos de interface; os valores são os do registro da execução).
const STATUS_OPTIONS = [
  { value: "ok", label: "Sucesso" },
  { value: "error", label: "Erro" },
];

/** Filtros simples do histórico: cliente, ticket, tipo, versão e status. Listas vindas do catálogo e de /api/meta. */
export default function RunFilters({ catalog, filters, onChange, onClear }) {
  const { profiles, tickets, versions, meta } = catalog;
  const set = (key) => (value) => onChange({ ...filters, [key]: value });
  const active = Object.values(filters).some(Boolean);

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
      <button type="button" className="secondary outline filters-clear" disabled={!active} onClick={onClear}>
        Limpar
      </button>
    </div>
  );
}
