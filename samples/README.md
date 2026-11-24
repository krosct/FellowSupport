# samples

Exemplos reais de saída JSON do **FellowSupport**, selecionados a partir de `var/` para documentar os entregáveis do desafio técnico.
Todas as execuções foram feitas com o modelo real `deepseek/deepseek-v4.1-flash-1017` via OpenRouter (`provider: "openrouter"`,
`temperature: 0.1`, `max_tokens: 12000`, `structured_mode: "json_schema"`, `reasoning: "high"`). Cada arquivo de execução inclui
`prompt_messages` (mensagens exatas enviadas ao modelo), metadados de latência/tokens (`llm_calls`) e `cache_key`.

As notas do campo `evaluation` e as conclusões das comparações são avaliações manuais do candidato pela rubrica fixa
(`clarity`, `customer_fit`, `actionability`, de 1 a 5; total máximo 15). Nos arquivos de comparação, `run_path` referencia o caminho
original em `var/runs/` (pasta ignorada no git), e as 12 execuções utilizadas nas 3 comparações estão copiadas integralmente em
`evaluated_runs/`. A análise completa do experimento e dos trade-offs está em [`../PROMPT_ENGINEERING_NOTES.md`](../PROMPT_ENGINEERING_NOTES.md).

| Arquivo | O que é |
|---|---|
| `by_type/clarifying_questions.json` | Perguntas de esclarecimento · bianca × t-webhook · prompt v4 (14/15) |
| `by_type/diagnosis.json` | Diagnóstico · amanda × t-webhook · prompt v4 |
| `by_type/flow_summary.json` | Resumo visual do fluxo (grafo + ASCII em `rendered`) · amanda × t-webhook · prompt v4 |
| `by_type/resolution_steps.json` | Passo a passo · rafael × t-webhook · prompt v4 (15/15) |
| `cache_hit.json` | Acerto de cache (`cache_hit: true`): 0 chamadas ao LLM, 1 ms, origem `aba69b5c89e1` |
| `comparisons/bianca_t-webhook_clarifying_questions_v1_vs_v2_vs_v3_vs_v4.json` | Comparação bianca × t-webhook (clarifying_questions): v1=13 · v2=11 · v3=12 · v4=14 (vencedor: v4) |
| `comparisons/marta_t-2fa_diagnosis_v1_vs_v2_vs_v3_vs_v4.json` | Comparação marta × t-2fa (diagnosis): v1=10 · v2=10 · v3=14 · v4=11 (vencedor: v3) |
| `comparisons/rafael_t-webhook_resolution_steps_v1_vs_v2_vs_v3_vs_v4.json` | Comparação rafael × t-webhook (resolution_steps): v1=11 · v2=12 · v3=11 · v4=15 (vencedor: v4) |
| `error.json` | Execução com erro registrada (`status: "error"`): `InvalidLLMOutput` (corte por limite de raciocínio do provedor) |
| `evaluated_runs/bianca_t-webhook_clarifying_questions_v1.json` | Execução avaliada (v1, 13/15): bianca × t-webhook · clarifying_questions |
| `evaluated_runs/bianca_t-webhook_clarifying_questions_v2.json` | Execução avaliada (v2, 11/15): bianca × t-webhook · clarifying_questions |
| `evaluated_runs/bianca_t-webhook_clarifying_questions_v3.json` | Execução avaliada (v3, 12/15): bianca × t-webhook · clarifying_questions |
| `evaluated_runs/bianca_t-webhook_clarifying_questions_v4.json` | Execução avaliada (v4, 14/15): bianca × t-webhook · clarifying_questions |
| `evaluated_runs/marta_t-2fa_diagnosis_v1.json` | Execução avaliada (v1, 10/15): marta × t-2fa · diagnosis |
| `evaluated_runs/marta_t-2fa_diagnosis_v2.json` | Execução avaliada (v2, 10/15): marta × t-2fa · diagnosis |
| `evaluated_runs/marta_t-2fa_diagnosis_v3.json` | Execução avaliada (v3, 14/15): marta × t-2fa · diagnosis |
| `evaluated_runs/marta_t-2fa_diagnosis_v4.json` | Execução avaliada (v4, 11/15): marta × t-2fa · diagnosis |
| `evaluated_runs/rafael_t-webhook_resolution_steps_v1.json` | Execução avaliada (v1, 11/15): rafael × t-webhook · resolution_steps |
| `evaluated_runs/rafael_t-webhook_resolution_steps_v2.json` | Execução avaliada (v2, 12/15): rafael × t-webhook · resolution_steps |
| `evaluated_runs/rafael_t-webhook_resolution_steps_v3.json` | Execução avaliada (v3, 11/15): rafael × t-webhook · resolution_steps |
| `evaluated_runs/rafael_t-webhook_resolution_steps_v4.json` | Execução avaliada (v4, 15/15): rafael × t-webhook · resolution_steps |
