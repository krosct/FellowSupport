Tarefa: formular as perguntas de esclarecimento que o atendimento precisa fazer ao cliente, priorizadas, pedindo somente o que for necessário para avançar, com as perguntas escritas conforme as regras de adaptação do perfil.

Critérios de prioridade, nesta ordem:
1. Primeiro, a pergunta cuja resposta mais separa as hipóteses prováveis do problema.
2. Em empate, a mais fácil de o cliente responder agora, sozinho, no nível técnico dele (para leigo, algo que ele vê na tela ou no aparelho; para avançado, pode pedir comando, log ou código de erro).

Estrutura:
1. Perguntas: de $min_questions a $max_questions, da mais para a menos importante. Cada uma tem a prioridade (1 é a mais importante), a pergunta, o motivo de ela ser necessária e quais hipóteses a resposta ajuda a confirmar ou descartar.
2. Avanço sem respostas: diga se o atendimento consegue avançar sem as respostas e explique em uma frase o que dá para fazer já ou por que as respostas são indispensáveis.

Restrições do canal: $channel_format

Formato de saída: responda somente com um objeto JSON, sem texto fora dele, neste formato:
{
  "questions": [
    {"priority": 1, "question": "...", "why_it_matters": "...", "unlocks": "..."}
  ],
  "can_proceed_without_answers": false,
  "proceed_note": "..."
}

Regras: não pergunte o que o ticket já informa; cada pergunta pede uma única informação que o cliente consiga responder sozinho; numere as prioridades 1, 2, 3... na ordem em que as perguntas aparecem; nunca peça senha nem código de verificação; escreva em português do Brasil.

Autoverificação (faça em silêncio e não escreva a lista na resposta). Antes de responder, confira:
- a ordem segue os critérios de prioridade e as prioridades são 1, 2, 3...?
- vocabulário, extensão e formato seguem as regras do perfil (nível, estilo e canal)?
- nenhuma pergunta repete o ticket, e a resposta é só o JSON?
