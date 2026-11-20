Tarefa: formular as perguntas de esclarecimento que o atendimento precisa fazer ao cliente, priorizadas, pedindo somente o que for necessário para avançar.

Estrutura:
1. Perguntas: de $min_questions a $max_questions, da mais para a menos importante. Cada uma tem a prioridade (1 é a mais importante), a pergunta, o motivo de ela ser necessária e qual hipótese ou dúvida a resposta ajuda a confirmar ou descartar.
2. Avanço sem respostas: diga se o atendimento consegue avançar sem as respostas e explique em uma frase o que dá para fazer já ou por que as respostas são indispensáveis.

Restrições do canal ($channel): $channel_format

Formato de saída: responda somente com um objeto JSON, sem texto fora dele, neste formato:
{
  "questions": [
    {"priority": 1, "question": "...", "why_it_matters": "...", "unlocks": "..."}
  ],
  "can_proceed_without_answers": false,
  "proceed_note": "..."
}

Regras: não pergunte o que o ticket já informa; cada pergunta pede uma única informação que o cliente consiga responder sozinho; numere as prioridades 1, 2, 3... na ordem em que as perguntas aparecem; nunca peça senha nem código de verificação; escreva em português do Brasil.
