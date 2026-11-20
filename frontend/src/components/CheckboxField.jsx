/** Caixa de seleção com rótulo e dica curta opcional. `disabled` mostra a dica como motivo. */
export default function CheckboxField({ label, hint, checked, onChange, disabled = false }) {
  return (
    <label className="checkbox-field">
      <input type="checkbox" checked={checked} disabled={disabled} onChange={(event) => onChange(event.target.checked)} />
      <span>
        {label}
        {hint && <small className="hint"> {hint}</small>}
      </span>
    </label>
  );
}
