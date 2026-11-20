import Badge from "./Badge.jsx";

/** Cabeçalho do app: marca, descrição curta e o provedor de LLM em uso (vem de /api/meta). */
export default function Header({ llm }) {
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
          <Badge kind="neutral">
            Provedor: {llm.provider}
          </Badge>
        )}
      </div>
    </header>
  );
}
