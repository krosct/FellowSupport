/**
 * Lista curta de textos. `kind` escolhe o marcador por CSS: "for" (+), "against" (−) ou "neutral" (•).
 * `empty` aparece quando não há itens.
 */
export default function BulletList({ items, kind = "neutral", empty = "Nenhum." }) {
  if (!items?.length) return <p className="hint">{empty}</p>;
  return (
    <ul className="bullet-list" data-kind={kind}>
      {items.map((item, index) => (
        <li key={index}>{item}</li>
      ))}
    </ul>
  );
}
