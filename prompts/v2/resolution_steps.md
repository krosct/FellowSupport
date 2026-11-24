Tarefa: escrever o passo a passo para resolver o problema relatado no ticket, para o cliente executar, adaptado ao perfil dele (nível técnico e estilo de comunicação).

Estrutura:
1. Abertura: uma ou duas frases que reconhecem o problema e dizem o que será feito.
2. Passos: de $min_steps a $max_steps passos, na ordem de execução, a partir do mais simples e seguro. Cada passo tem título curto, instrução, resultado esperado (o que o cliente deve ver se deu certo) e o que fazer se falhar.
3. Quando escalar: a situação em que o caso deve ir para outro nível de atendimento, e para quem.
4. Fechamento: uma ou duas frases com a próxima ação combinada.

Restrições do canal ($channel): $channel_format

Formato de saída: responda somente com um objeto JSON, sem texto fora dele, neste formato:
{
  "opening": "...",
  "steps": [
    {"order": 1, "title": "...", "instruction": "...", "expected_result": "...", "if_it_fails": "..."}
  ],
  "when_to_escalate": "...",
  "closing": "..."
}

Regras: numere os passos 1, 2, 3... na ordem; cada passo pede uma única ação; não repita como passo algo que o ticket já informa ter falhado sem explicar o que mudou; em if_it_fails, indique uma alternativa prática ou quando pular/escalar; use apenas o que o ticket informa e recursos que o produto realmente oferece, sem inventar telas, menus ou botões; não peça senha nem código de verificação; escreva em português do Brasil.
