/**
 * Campo de seleção com rótulo. Se `emptyLabel` vier, a primeira opção (valor vazio) significa "sem filtro".
 * Usado no seletor de conteúdo e nos filtros do histórico. `options` é `[{ value, label }]`.
 */
export default function SelectField({ label, value, onChange, options, emptyLabel }) {
  return (
    <label className="select-field">
      <span className="summary-label">{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {emptyLabel != null && <option value="">{emptyLabel}</option>}
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}
