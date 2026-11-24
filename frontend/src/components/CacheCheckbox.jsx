import CheckboxField from "./CheckboxField.jsx";

/**
 * Opção "Usar cache" da aba Gerar. Marcada, consulta o cache antes de gerar; desmarcada,
 * gera de novo. Em ambos os casos o resultado é gravado no cache (ADR 0035).
 */
export default function CacheCheckbox({ checked, onChange }) {
  return <CheckboxField label="Usar cache" hint="" checked={checked} onChange={onChange} />;
}
