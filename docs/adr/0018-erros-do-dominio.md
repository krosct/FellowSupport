# ADR 0018 · Exceções do domínio mapeadas para HTTP e CLI

- **Status**: Aceito
- **Data**: 2026-11-20

## Contexto

Falhas esperadas (provedor fora do ar, limite de taxa, saída inválida, entidade inexistente, entrada inválida) precisam de mensagens claras e consistentes no site e na CLI.

## Opções consideradas

### Exceções próprias (`Unauthorized`, `Forbidden`, `NotFound`, `CacheReplaceRequired`, `ValidationFailed`, `LLMRateLimited`, `InvalidLLMOutput`, `LLMUnavailable`) mapeadas para 401, 403, 404, 409, 422, 429, 502 e 503 e para códigos de saída da CLI; execuções com erro gravadas com `status: "error"` e fora do cache

- **Prós**: Mensagens úteis; a camada de entrada traduz sem conhecer detalhes do SDK; erros ficam auditáveis.
- **Contras**: Uma hierarquia de exceções a manter.
- **Custo**: Baixo.
- **Risco**: Baixo.

### Deixar as exceções estourarem

- **Prós**: Menos código.
- **Contras**: Respostas 500 genéricas e mensagens ruins para o usuário.
- **Custo**: Baixo.
- **Risco**: Alto: experiência ruim e difícil diagnóstico.

### Retornar códigos de erro em dicionários

- **Prós**: Sem exceções.
- **Contras**: Fácil esquecer de checar; polui o fluxo normal.
- **Custo**: Médio.
- **Risco**: Médio.

## Decisão

Definir as exceções em `domain/errors.py` e traduzi-las nos adaptadores de API e CLI. Erros de geração são persistidos e nunca alimentam o cache.

## Por que vence

- **O que ganha e o que perde**: Ganha clareza e robustez. Perde alguma verbosidade.
- **Por que compensa**: Compensa porque separa falhas de domínio da camada de transporte, evita respostas 500 opacas e mantém erros auditáveis fora do cache.

## Consequências

O domínio lança só exceções do próprio pacote; adaptadores convertem erros de bibliotecas nelas.

## Como verificar

Testes parametrizados: cada exceção produz o status HTTP e o código de saída da CLI esperados; execução com erro não cria entrada no cache.
