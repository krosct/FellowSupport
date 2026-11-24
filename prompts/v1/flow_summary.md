Tarefa: resumir o fluxo de atendimento do problema relatado no ticket como uma árvore de decisão, que mostre como chegar da queixa do cliente até a resolução ou o escalonamento.

Estrutura: um grafo de $min_nodes a $max_nodes nós e as arestas entre eles.
- Tipos de nó: "start" (o início, com a queixa do cliente), "action" (uma ação a executar), "decision" (uma pergunta cuja resposta escolhe o caminho) e "end" (um desfecho: resolvido ou escalado).
- Cada aresta liga um nó de origem a um de destino. Nas arestas que saem de uma decisão, o rótulo nomeia o ramo ("Sim" ou "Não"); nas demais, o rótulo é uma string vazia.

Restrições do canal ($channel): $channel_format

Os rótulos dos nós têm no máximo $label_max_chars caracteres.

Formato de saída: responda somente com um objeto JSON, sem texto fora dele, neste formato:
{
  "nodes": [
    {"id": "n1", "type": "start", "label": "..."},
    {"id": "n2", "type": "decision", "label": "..."},
    {"id": "n3", "type": "action", "label": "..."},
    {"id": "n4", "type": "end", "label": "..."}
  ],
  "edges": [
    {"source": "n1", "target": "n2", "label": ""},
    {"source": "n2", "target": "n3", "label": "Não"},
    {"source": "n2", "target": "n4", "label": "Sim"},
    {"source": "n3", "target": "n4", "label": ""}
  ]
}

Regras: exatamente um nó "start", sem arestas de entrada; ao menos um nó "end", sem arestas de saída; "start" e "action" têm exatamente uma aresta de saída; "decision" tem duas ou mais, todas com rótulo diferente; todo nó é alcançável a partir do "start"; o fluxo não tem ciclos; todo id usado em uma aresta existe em "nodes"; use apenas o que o ticket informa e não invente telas ou funcionalidades; escreva em português do Brasil. O desenho em texto será feito por outro programa, então não desenhe nada: entregue só o JSON.
