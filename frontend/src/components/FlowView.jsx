/**
 * Fluxograma em ASCII, já desenhado pelo backend (`rendered`). Fica em um `<pre>` com rolagem horizontal
 * própria: um fluxo largo nunca alarga a página. `tabIndex` permite rolar com o teclado.
 */
export default function FlowView({ rendered }) {
  if (!rendered) return <p className="hint">Fluxograma indisponível.</p>;
  return (
    <div className="flow-view">
      <pre className="flow-ascii" tabIndex={0} aria-label="Fluxograma de decisão">
        {rendered}
      </pre>
    </div>
  );
}
