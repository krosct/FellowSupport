/**
 * Campo de texto com rótulo e contador de caracteres. Uma linha por padrão; `multiline` vira uma caixa de texto.
 * `maxLength` vem de /api/meta.
 */
export default function TextField({
  label,
  value,
  onChange,
  maxLength,
  placeholder,
  multiline = false,
  rows = 8,
  className = "",
}) {
  const Control = multiline ? "textarea" : "input";
  return (
    <label className={`form-field ${className}`.trim()}>
      {label}
      <Control
        {...(multiline ? { rows } : { type: "text" })}
        maxLength={maxLength}
        placeholder={placeholder}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
      <small className="counter">
        {value.length} / {maxLength}
      </small>
    </label>
  );
}
