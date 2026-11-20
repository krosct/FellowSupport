# ADR 0007 · Quatro geradores independentes sobre um núcleo comum

- **Status**: Aceito
- **Data**: 2026-11-20

## Contexto

O PDF pede quatro funções ou estratégias separadas, cada uma com prompt adequado, mesmo compartilhando componentes. Também é desejável gerar todas de uma vez.

## Opções consideradas

### Quatro geradores independentes sobre `_generate`; opção `all` em paralelo com `ThreadPoolExecutor`

- **Prós**: Chamadas independentes: cache por tipo, falha isolada e menor latência total.
- **Contras**: Os quatro conteúdos podem divergir levemente entre si (por exemplo, a conclusão do diagnóstico e os passos).
- **Custo**: Baixo.
- **Risco**: Baixo: divergência documentada como limitação.

### Geração em cadeia (o diagnóstico alimenta os demais)

- **Prós**: Maior coerência entre os conteúdos.
- **Contras**: Acoplamento: uma chamada depende da anterior; falha em cascata; cache por tipo piora; latência soma.
- **Custo**: Médio.
- **Risco**: Médio: erro no diagnóstico contamina tudo.

### Uma única chamada gerando os quatro conteúdos

- **Prós**: Menos chamadas e coerência interna.
- **Contras**: Prompt gigante (contra a recomendação do PDF), saída longa que estoura `max_tokens`, impossível comparar prompts por tipo.
- **Custo**: Baixo.
- **Risco**: Alto: perde a avaliação por conteúdo.

## Decisão

Quatro funções públicas (`generate_diagnosis`, `generate_resolution_steps`, `generate_clarifying_questions`, `generate_flow_summary`) sobre um núcleo `_generate` com cache, chamada, validação e persistência.

## Por que vence

- **O que ganha e o que perde**: Ganha isolamento, cache granular e comparação por tipo. Perde garantia de coerência cruzada.
- **Por que compensa**: Compensa porque a comparação de prompts é por tipo de conteúdo e a divergência é pequena com temperatura baixa.

## Consequências

A limitação de coerência cruzada aparece nas notas de engenharia de prompt.

## Como verificar

Teste de cada gerador isolado e da opção `all` com o LLM falso, conferindo uma execução por tipo.
