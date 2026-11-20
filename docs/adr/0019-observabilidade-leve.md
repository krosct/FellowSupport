# ADR 0019 · Observabilidade leve com logging e métricas por execução

- **Status**: Aceito
- **Data**: 2026-11-20

## Contexto

O PDF considera observabilidade um extra. É útil saber latência, consumo de tokens e o modelo realmente usado, sem infraestrutura adicional.

## Opções consideradas

### `logging` da biblioteca padrão e campos `latency_ms`, `usage`, `model_used` e `cache_hit` em cada execução

- **Prós**: Sem dependências; os dados ficam no próprio JSON da execução e permitem comparar custo e latência entre versões.
- **Contras**: Sem painel nem agregação.
- **Custo**: Baixo.
- **Risco**: Baixo.

### OpenTelemetry com coletor e painel

- **Prós**: Rastreamento distribuído padronizado.
- **Contras**: Exagero para o escopo; várias dependências e infraestrutura.
- **Custo**: Alto.
- **Risco**: Médio.

### Sem observabilidade

- **Prós**: Nenhum custo.
- **Contras**: Sem evidência de latência ou tokens; difícil depurar modelos gratuitos instáveis.
- **Custo**: Baixo.
- **Risco**: Médio.

## Decisão

Usar `logging` padrão (nível por `LOG_LEVEL`) e registrar latência, uso de tokens, modelo efetivo e cache hit em cada execução.

## Por que vence

- **O que ganha e o que perde**: Ganha diagnóstico barato e dados para a comparação. Perde métricas agregadas.
- **Por que compensa**: Compensa porque o escopo não justifica infraestrutura de observabilidade.

## Consequências

Logs nunca incluem a chave nem o texto completo do ticket em nível INFO.

## Como verificar

Teste: o registro da execução contém os quatro campos; log de inicialização não contém a chave.
