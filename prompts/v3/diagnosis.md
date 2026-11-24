Tarefa: produzir o diagnóstico do problema relatado no ticket, decomposto nas partes abaixo.

1. Hipóteses: de $min_hypotheses a $max_hypotheses causas possíveis, da mais para a menos provável. Para cada uma, informe um id ("H1", "H2", ...), a descrição, a probabilidade estimada (percentual inteiro de 0 a 100) de acordo com as evidências do ticket a favor e contra a hipótese.
2. Evidências disponíveis: fatos observáveis que o próprio ticket informa.
3. Informações faltantes: até $max_missing_info dados que o ticket não traz e que ajudariam a decidir entre as hipóteses, cada um com o motivo de ser importante.
4. Conclusão provável: um resumo curto, o id da hipótese escolhida e a confiança ($confidence_levels).
5. Resumo para o cliente: um texto curto que explique o diagnóstico ao cliente.

Restrições do canal em customer_summary ($channel): $channel_format Se o canal for falado (telefone), escreva horários e siglas por extenso no resumo ao cliente.

Formato de saída: responda somente com um objeto JSON, sem texto fora dele, neste formato:
{
  "hypotheses": [
    {"id": "H1", "description": "...", "probability_pct": 0, "evidence_for": ["..."], "evidence_against": ["..."]}
  ],
  "available_evidence": ["..."],
  "missing_information": [{"item": "...", "why_it_matters": "..."}],
  "probable_conclusion": {"summary": "...", "hypothesis_id": "H1", "confidence": "..."},
  "customer_summary": "..."
}

Regras: em evidence_for e evidence_against, cite apenas fatos literais do ticket (sem suposições ou interpretações); use lista vazia quando não houver evidência a favor ou contra; os ids da conclusão e das hipóteses devem coincidir; escreva em português do Brasil.
