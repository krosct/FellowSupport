# ADR 0010 · Chave de cache canônica com SHA-256

- **Status**: Aceito
- **Data**: 2026-11-20

## Contexto

Execuções com entrada, versão de prompt e configurações equivalentes devem reaproveitar o resultado, e uma mudança relevante em qualquer insumo deve invalidar o cache.

## Opções consideradas

### SHA-256 do JSON canônico de {conteúdo do perfil, ticket normalizado, tipo, versão, `prompt_sha256`, provedor, modelo, temperatura, `max_tokens`, modo estruturado}

- **Prós**: Invalida corretamente quando perfil, prompt ou configuração mudam; determinística; independente da ordem das chaves.
- **Contras**: Qualquer ajuste de parâmetro cria nova entrada; sem TTL, o resultado antigo vale para sempre.
- **Custo**: Baixo.
- **Risco**: Baixo: sem TTL, assume-se geração determinística o bastante com temperatura baixa (documentado).

### Chave composta só de ids (perfil, ticket, versão)

- **Prós**: Chave curta e legível.
- **Contras**: Não invalida quando um perfil, ticket ou prompt é editado; devolve resultado desatualizado.
- **Custo**: Baixo.
- **Risco**: Alto: cache obsoleto sem aviso.

### Cache com TTL

- **Prós**: Renova resultados periodicamente.
- **Contras**: Introduz não determinismo na reprodutibilidade; complexidade de expiração.
- **Custo**: Médio.
- **Risco**: Médio: comparações perdem estabilidade.

## Decisão

Chave SHA-256 sobre o JSON canônico (chaves ordenadas, sem espaços) dos campos listados. Um cache hit também grava uma execução com `cache_hit: true` e `source_run_id`.

## Por que vence

- **O que ganha e o que perde**: Ganha correção da invalidação e evidência auditável de cada reaproveitamento. Perde renovação automática.
- **Por que compensa**: Compensa porque o checklist do PDF pede evidência de que o cache evita ao menos uma chamada equivalente.

## Consequências

A função de chave vive em `domain/cache_key.py` (domínio puro).

## Como verificar

Teste por campo: alterar cada insumo muda a chave; reordenar chaves não muda; segunda geração idêntica retorna `cache_hit: true` sem chamar o LLM.
