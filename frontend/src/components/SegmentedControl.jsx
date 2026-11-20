/**
 * Alternância entre poucas opções (abas simples). Usa botões com aria-pressed para ficar acessível.
 * `wrap` deixa as opções quebrarem de linha quando os rótulos são longos (ex.: telas estreitas).
 */
export default function SegmentedControl({ options, value, onChange, label, wrap = false }) {
  return (
    <div className="segmented" data-wrap={wrap} role="group" aria-label={label}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          className="segmented-item"
          aria-pressed={value === option.value}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
