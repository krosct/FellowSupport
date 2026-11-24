/** Cabeçalho do app: marca, descrição curta, botão de provedor/modelo (abre chaves da sessão) e navegação. */
export default function Header({ llm, hasSessionKeys, onOpenKeys, nav }) {
  return (
    <header className="app-header">
      <div className="container app-header-inner">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            FS
          </span>
          <div>
            <h1>FellowSupport</h1>
            <p className="hint">Suporte técnico adaptado ao perfil de cada cliente</p>
          </div>
        </div>
        {llm && (
          <button
            type="button"
            className="header-llm-btn"
            onClick={onOpenKeys}
            aria-label="Configurar chaves da sessão (provedor e modelo)"
          >
            <span className="header-llm">
              <span>Provedor: {llm.provider}</span>
              {llm.model && <span className="header-llm-model">Modelo: {llm.model}</span>}
              <span className="header-llm-keys">
                {hasSessionKeys ? "Chaves: sessão ativa" : "Configurar chaves"}
              </span>
            </span>
          </button>
        )}
      </div>
      {nav && <nav className="container app-nav" aria-label="Seções">{nav}</nav>}
    </header>
  );
}
