# ADR 0008 · Fluxograma: árvore de decisão em JSON e ASCII gerado por código

- **Status**: Aceito
- **Data**: 2026-11-20

## Contexto

O quarto conteúdo é um resumo visual do fluxo. Modelos de linguagem desalinham desenhos em texto e a saída precisa ser verificável.

## Opções consideradas

### O LLM devolve uma árvore de decisão (nós e arestas) e o código desenha o ASCII

- **Prós**: Desenho sempre alinhado e testável por snapshot; a representação em nós e arestas é estruturada e reaproveitável tanto na CLI quanto na web.
- **Contras**: Exige um schema de grafo e um renderizador; o desenho é menos livre.
- **Custo**: Médio: schema, validação e renderizador.
- **Risco**: Baixo: grafos inválidos (nó inexistente, ciclo) são rejeitados na validação.

### O LLM desenha o ASCII diretamente

- **Prós**: Nenhum código adicional.
- **Contras**: Alinhamento instável, difícil de validar e de testar; varia entre execuções.
- **Custo**: Baixo.
- **Risco**: Alto: saída ilegível em alguns casos.

### Diagrama Mermaid gerado pelo LLM

- **Prós**: Renderização gráfica bonita na web.
- **Contras**: Exige biblioteca no front; não atende ao fluxograma ASCII na CLI; sintaxe inválida é comum.
- **Custo**: Médio.
- **Risco**: Médio: erros de sintaxe do modelo.

## Decisão

O schema `FlowSummary` descreve nós e arestas; `domain/flow_render.py` converte para ASCII de forma pura e determinística.

## Por que vence

- **O que ganha e o que perde**: Ganha determinismo e verificabilidade. Perde liberdade visual do desenho livre.
- **Por que compensa**: Compensa porque entrega tanto a descrição estruturada (JSON de nós e arestas) quanto o fluxograma em ASCII a partir de uma única fonte determinística.

## Consequências

Teste de snapshot do renderizador e validação de grafos.

## Como verificar

Testes de snapshot com grafos de exemplo e testes de rejeição de nó inexistente e de ciclo.
