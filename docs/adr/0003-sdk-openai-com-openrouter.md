# ADR 0003 · SDK openai com base_url do OpenRouter

- **Status**: Aceito
- **Data**: 2026-11-20

## Contexto

O sistema precisa chamar modelos de linguagem pela rede com timeout, retentativas e tratamento de erros, e deve permitir trocar de provedor (por exemplo para um modelo pago de baixo custo) sem alterar código.

## Opções consideradas

### SDK `openai` apontando para um endpoint compatível

- **Prós**: Retry com backoff, timeout e exceções tipadas prontos; trocar de provedor exige só `LLM_BASE_URL` e `LLM_MODEL`; OpenRouter, DeepSeek e OpenAI usam o mesmo protocolo.
- **Contras**: Dependência relativamente grande; nem todo provedor compatível implementa 100% dos parâmetros.
- **Custo**: Baixo: uma dependência.
- **Risco**: Baixo: diferenças entre provedores aparecem em `response_format`, tratadas pelo modo estruturado (ADR 0004).

### `httpx` direto

- **Prós**: Menos dependências e controle total das requisições.
- **Contras**: É preciso reimplementar retry, timeout, interpretação de erros e streaming; mais código a manter e testar.
- **Custo**: Médio: código e testes próprios.
- **Risco**: Médio: bugs em casos de borda de rede e de erros do provedor.

### LiteLLM

- **Prós**: Interface única para dezenas de provedores.
- **Contras**: Muitas dependências transitivas; superfície grande para um uso que cabe em uma chamada; atualizações frequentes.
- **Custo**: Médio: peso de instalação e de auditoria.
- **Risco**: Médio: quebras entre versões.

### SDKs nativos de cada provedor

- **Prós**: Acesso aos recursos específicos de cada um.
- **Contras**: Um adaptador e uma dependência por provedor; trocar de provedor exige código.
- **Custo**: Alto.
- **Risco**: Médio: comportamento divergente entre adaptadores.

## Decisão

Usar o SDK `openai` configurado com `base_url` e chave do `.env`, encapsulado no adaptador `adapters/llm/openai_compat.py` atrás da porta `LLMClient`.

## Por que vence

- **O que ganha e o que perde**: Ganha troca de provedor só por configuração e tratamento de erro maduro. Perde minimalismo de dependências.
- **Por que compensa**: Compensa porque reimplementar retry e tratamento de erros custa mais que manter uma dependência estável, mantendo a troca de provedor e modelo via `.env` como definido pelo projeto.

## Consequências

O domínio só conhece a porta `LLMClient`. Testes do adaptador usam `httpx.MockTransport` (ADR 0016).

## Como verificar

Teste do adaptador com transporte simulado cobrindo sucesso, 429, 5xx e timeout; trocar `LLM_BASE_URL` e `LLM_MODEL` no `.env` sem alterar código.
