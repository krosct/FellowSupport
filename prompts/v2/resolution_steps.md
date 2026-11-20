Tarefa: escrever o passo a passo para resolver o problema relatado no ticket, para o cliente executar, seguindo as regras de adaptação do perfil.

Estrutura:
1. Abertura: uma ou duas frases que reconhecem o problema e dizem o que será feito.
2. Passos: de $min_steps a $max_steps passos, na ordem de execução, do mais simples e seguro ao mais invasivo. Pule o que o ticket já responde (não peça para conferir o que o cliente já informou) e comece pelo passo com mais chance de resolver. Cada passo tem título curto, instrução e uma verificação:
   - resultado esperado: algo que o cliente consegue ver ou testar na hora para saber se o passo funcionou;
   - se falhar: uma ação concreta ou o encaminhamento para escalar; nunca apenas "vá para o próximo passo".
3. Quando escalar: a situação em que o caso deve ir para outro nível de atendimento, e para quem.
4. Fechamento: uma ou duas frases com a próxima ação combinada.

Restrições do canal: $channel_format

Formato de saída: responda somente com um objeto JSON, sem texto fora dele, neste formato:
{
  "opening": "...",
  "steps": [
    {"order": 1, "title": "...", "instruction": "...", "expected_result": "...", "if_it_fails": "..."}
  ],
  "when_to_escalate": "...",
  "closing": "..."
}

Regras: numere os passos 1, 2, 3... na ordem; cada passo pede uma única ação; use apenas o que o ticket informa e recursos que o produto realmente oferece, sem inventar telas, menus ou botões; não peça senha nem código de verificação; escreva em português do Brasil.

Autoverificação (faça em silêncio e não escreva a lista na resposta). Antes de responder, confira:
- vocabulário, extensão e formato seguem as regras do perfil (nível, estilo e canal)?
- todo passo tem uma verificação observável e um "se falhar" que diz o que fazer?
- nenhum passo repete o que o ticket já informa, e a resposta é só o JSON?
