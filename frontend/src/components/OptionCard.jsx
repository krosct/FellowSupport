/**
 * Opção de escolha única em forma de cartão (radio nativo por baixo: teclado e leitor de tela funcionam).
 * Reutilizado pelos seletores de perfil e de ticket.
 */
export default function OptionCard({ name, value, checked, onChange, children }) {
  return (
    <label className="option-card" data-checked={checked}>
      <input type="radio" name={name} value={value} checked={checked} onChange={() => onChange(value)} />
      <span className="option-card-body">{children}</span>
    </label>
  );
}
