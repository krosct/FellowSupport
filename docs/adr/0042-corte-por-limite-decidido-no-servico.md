# ADR 0042 · Resposta cortada decidida no serviço, com gasto e provedor registrados

- **Status**: Aceito (complementa os ADRs [0003](0003-sdk-openai-com-openrouter.md), [0004](0004-saida-estruturada.md) e [0026](0026-modelo-padrao.md))
- **Data**: 2026-11-23

## Contexto

Quando o adaptador `openai_compat` levantava `InvalidLLMOutput` diretamente ao receber `finish_reason=length` sem JSON, três problemas ocorriam:

1. A mensagem chamava de "limite" o `completion_tokens` gasto (ex.: 2400) e mandava aumentar `LLM_MAX_TOKENS`, mesmo quando o limite configurado era maior (ex.: 12000).
2. A exceção subia antes de o `LLMResult` existir: o serviço não somava o gasto, e o registro ficava com `usage: {}` e `model_used: null`, embora os tokens tenham sido cobrados.
3. O provedor roteado que atendeu não era gravado. O OpenRouter distribui o mesmo modelo entre dezenas de provedores e um deles pode impor um teto menor do que `LLM_MAX_TOKENS`; sem o provedor no registro, não há como apontar qual deles corta.

## Opções consideradas

### Adaptador devolve `finish_reason`, provedor e id; o serviço decide e registra (escolhida)

- **Prós**: O serviço soma o gasto antes de falhar e grava cada chamada em `llm_calls` (provedor, id da geração, razão de parada, uso, latência e motivo da recusa). A mensagem compara o gasto com o `max_tokens` configurado e só manda aumentar o limite quando o corte foi nele. A regra fica no domínio (`truncation_message`), testável sem rede.
- **Contras**: Muda o contrato da porta: quem implementar `LLMClient` precisa preencher `finish_reason`.
- **Custo**: Baixo: três campos opcionais em `LLMResult` e o modelo `LlmCall` no registro.
- **Risco**: Baixo: os campos têm padrão, e registros antigos continuam válidos (`llm_calls` vazio).

### Anexar o uso à exceção levantada pelo adaptador

- **Prós**: Mudança pequena no adaptador.
- **Contras**: A exceção do domínio passaria a carregar dados de infraestrutura, e o serviço teria dois caminhos para contabilizar uma chamada.
- **Custo**: Baixo.
- **Risco**: Médio: é fácil esquecer o caminho da exceção numa mudança futura e voltar a perder o gasto.

### Manter como está e só corrigir o texto da mensagem

- **Prós**: Sem mudança de contrato.
- **Contras**: Continua perdendo o gasto e o provedor, justamente os dados que explicam a falha.
- **Custo**: Muito baixo.
- **Risco**: Alto: a próxima ocorrência continua sem diagnóstico.

## Decisão

`LLMResult` ganha `finish_reason`, `provider_used` (campo `provider` do OpenRouter) e `response_id`. O adaptador não
levanta mais nada no corte. O serviço, em `_attempt`, contabiliza a chamada e, se for `length` sem JSON, levanta
`InvalidLLMOutput` com a mensagem de `truncation_message`. O registro da execução ganha `llm_calls`. O corte continua
sem tentativa de reparo, evitando gastar uma chamada extra que bateria no mesmo limite.

## Por que vence

- **O que ganha e o que perde**: Ganha o gasto real das execuções com erro, a identificação do provedor e um remédio correto na mensagem. Perde a simplicidade de um adaptador que decidia sozinho.
- **Por que compensa**: Uma falha intermitente que depende do roteamento só se diagnostica com o provedor e o id da geração registrados.

## Consequências

- O registro com erro passa a ter `usage`, `model_used` e `llm_calls` preenchidos.
- Com o `response_id` dá para consultar a geração no provedor.
- Repetir a chamada no corte abaixo do limite (outro provedor pode atender) fica como decisão futura, com custo a medir.

## Como verificar

`pytest -q tests/test_observability.py tests/test_llm_openai_compat.py`: a execução cortada grava o uso, o modelo e o
provedor sem fazer reparo; a mensagem distingue o corte no limite configurado do corte imposto pelo provedor.
