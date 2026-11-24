import SelectField from "./SelectField.jsx";

/**
 * Paginação de uma listagem: total, página atual, Anterior/Próxima e itens por página. Os tamanhos aceitos vêm de
 * /api/meta (`limits.page_sizes`), os mesmos do `--limit` da CLI. `singular`/`plural` nomeiam os itens.
 */
export default function Pagination({ page, pageSize, total, pageSizes, onPageChange, onPageSizeChange, singular, plural }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return (
    <nav className="pagination" aria-label={`Páginas de ${plural}`}>
      <p className="hint pagination-info" aria-live="polite">
        {total} {total === 1 ? singular : plural} · Página {page} de {pages}
      </p>
      <div className="pagination-controls">
        <button type="button" className="secondary outline" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>
          Anterior
        </button>
        <button type="button" className="secondary outline" disabled={page >= pages} onClick={() => onPageChange(page + 1)}>
          Próxima
        </button>
        <SelectField
          label="Por página"
          value={String(pageSize)}
          onChange={(value) => onPageSizeChange(Number(value))}
          options={pageSizes.map((size) => ({ value: String(size), label: String(size) }))}
        />
      </div>
    </nav>
  );
}
