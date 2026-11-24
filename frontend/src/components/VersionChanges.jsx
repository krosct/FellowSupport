/**
 * O que mudou nas versões derivadas (`changes` do meta.json), de forma compacta: uma linha por mudança e, ao abrir, o
 * porquê e o efeito esperado na rubrica. Ajuda quem avalia a entender a diferença entre as saídas.
 * Mostra só as versões com `based_on` (a linha de base não tem o que comparar).
 */
export default function VersionChanges({ versions }) {
  const derived = versions.filter((version) => version.based_on);
  if (derived.length === 0) return null;
  return (
    <div className="stack">
      {derived.map((version) => (
        <details key={version.version} className="version-changes">
          <summary>
            O que mudou na {version.version} em relação à {version.based_on} ({version.changes.length})
          </summary>
          <ul className="change-list">
            {version.changes.map((change, index) => (
              <li key={index}>
                <details className="change">
                  <summary>
                    <span className="change-what">{change.what}</span>
                  </summary>
                  <dl>
                    <dt>Por quê</dt>
                    <dd>{change.why}</dd>
                    <dt>Efeito esperado</dt>
                    <dd>{change.expected_effect}</dd>
                  </dl>
                </details>
              </li>
            ))}
          </ul>
        </details>
      ))}
    </div>
  );
}
