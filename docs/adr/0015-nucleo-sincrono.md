# ADR 0015 · Núcleo síncrono com endpoints def

- **Status**: Aceito
- **Data**: 2026-11-20

## Contexto

As chamadas ao LLM são o gargalo e bloqueiam por I/O. É preciso decidir entre código síncrono e assíncrono em todo o núcleo.

## Opções consideradas

### Núcleo síncrono; endpoints `def` do FastAPI rodam em threadpool; `all` usa `ThreadPoolExecutor`

- **Prós**: Portas e testes simples; fácil de depurar e de aprender; sem contaminação de `async` pelo domínio.
- **Contras**: Menor eficiência com muitas conexões simultâneas.
- **Custo**: Baixo.
- **Risco**: Baixo: a escala é mínima e o limite de taxa protege o serviço.

### Async de ponta a ponta

- **Prós**: Melhor uso de recursos em alta concorrência.
- **Contras**: `async` contamina portas, serviços e testes; cliente assíncrono do SDK e mocks mais complexos.
- **Custo**: Médio.
- **Risco**: Médio: erros de concorrência e de loops de evento.

### Filas e workers em segundo plano

- **Prós**: Desacopla requisições longas.
- **Contras**: Infraestrutura extra desnecessária para o escopo e a escala do projeto.
- **Custo**: Alto.
- **Risco**: Médio.

## Decisão

Núcleo e portas síncronos. Concorrência apenas via threadpool do FastAPI e `ThreadPoolExecutor` na opção `all`.

## Por que vence

- **O que ganha e o que perde**: Ganha simplicidade e testabilidade. Perde escalabilidade em alta concorrência, fora do escopo.
- **Por que compensa**: Compensa porque simplicidade favorece a clareza do código e a explicação das decisões.

## Consequências

Portas não declaram `async`. Se a escala mudar, a troca será um ADR novo.

## Como verificar

Os endpoints de geração são `def`; teste da opção `all` com o LLM falso executando em paralelo sem condição de corrida nos arquivos.
