Tarefa: formular as perguntas de esclarecimento que o atendimento precisa fazer ao cliente, priorizadas, pedindo somente o que for necessário para avançar.

Estrutura:
1. Perguntas: de $min_questions a $max_questions, da mais para a menos importante.
2. Avanço sem respostas: diga se o atendimento consegue avançar sem as respostas e explique em uma frase o que dá para fazer já ou por que as respostas são indispensáveis.

Restrições do canal ($channel): $channel_format Se o canal for falado (telefone), escreva horários e siglas por extenso nos textos ao cliente.

Formato de saída: responda somente com um objeto JSON, sem texto fora dele, neste formato:
{
  "questions": [
    {"priority": 1, "question": "...", "why_it_matters": "...", "unlocks": "..."}
  ],
  "can_proceed_without_answers": false,
  "proceed_note": "..."
}

Regras: não pergunte o que o ticket já informa; use apenas o que o ticket informa, sem inventar telas ou elementos da interface; cada pergunta pede uma única informação que o cliente consiga responder sozinho (não peça dados internos da conta que o cliente não consegue consultar por estar sem acesso); numere as prioridades 1, 2, 3... na ordem em que as perguntas aparecem; mantenha proceed_note em uma única frase curta (até cerca de 200 caracteres), mesmo em perfis detalhados; nunca peça senha nem código de verificação; escreva em português do Brasil.
