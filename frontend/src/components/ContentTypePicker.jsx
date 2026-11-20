/**
 * Seletor do tipo de conteúdo. Os rótulos vêm de /api/meta: os quatro tipos e a opção "Todos" (`allOption`).
 */
export default function ContentTypePicker({ types, allOption, value, onChange }) {
  const options = [...types, allOption];
  return (
    <label className="type-picker">
      <span className="summary-label">Conteúdo</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}
