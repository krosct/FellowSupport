import DiagnosisView from "./DiagnosisView.jsx";
import StepsView from "./StepsView.jsx";
import QuestionsView from "./QuestionsView.jsx";
import FlowView from "./FlowView.jsx";

// Componente de visualização de cada tipo de conteúdo, escolhido pelo `content_type` da execução. Os rótulos
// dos tipos vêm de /api/meta; aqui só se liga o identificador ao componente.
const VIEWS = {
  diagnosis: ({ run, confidenceLevels }) => <DiagnosisView diagnosis={run.output} confidenceLevels={confidenceLevels} />,
  resolution_steps: ({ run }) => <StepsView steps={run.output} />,
  clarifying_questions: ({ run }) => <QuestionsView questions={run.output} />,
  flow_summary: ({ run }) => <FlowView rendered={run.rendered} />,
};

/**
 * Escolhe o componente certo para a saída de uma execução. Reutilizável em Gerar, Comparar e Histórico.
 * Tipo desconhecido ou execução sem saída mostra uma dica em vez de quebrar a tela.
 */
export default function OutputView({ run, confidenceLevels }) {
  const View = VIEWS[run.content_type];
  if (!View || !run.output) return <p className="hint">Sem conteúdo para mostrar.</p>;
  return <View run={run} confidenceLevels={confidenceLevels} />;
}
