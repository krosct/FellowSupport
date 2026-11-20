# ADR 0026 · Modelo padrão de geração e limite de tokens

- **Status**: Aceito
- **Data**: 2026-11-20

## Contexto

O modelo padrão precisa ser gratuito (`:free`), entregar JSON que valide contra o schema `Diagnosis` e escrever em português do Brasil. A Etapa 1 mediu dois candidatos com `scripts/smoke_llm.py` (uma chamada por execução, sem reparo, sem retentativas do SDK) e com a CLI real, usando o prompt `v1`, temperatura 0,1 e o modo `json_schema`. O orçamento da etapa era de 6 chamadas reais.

Medições (todas contadas):

| # | Modelo | Cenário | `max_tokens` | Resultado |
|---|---|---|---|---|
| 1 | `baidu/ernie-5.5-flash-preview:free` | marta × t-2fa | 1500 | Conteúdo vazio, `finish_reason=length`, 1500 tokens consumidos (10,1 s) |
| 2 | `baidu/ernie-5.5-flash-preview:free` | marta × t-2fa | 6000 | JSON válido, schema válido, 25,4 s, 5240 tokens de saída (3833 de raciocínio); 702 palavras, 98,7% das palavras funcionais reconhecidas em português; 4 hipóteses e 5 informações faltantes; um erro de grafia ("autentikador") |
| 3 | `baidu/ernie-5.5-flash-preview:free` | bianca × t-webhook | 8000 | Cortado: 8000 tokens, todos de raciocínio, sem JSON (37,3 s) |
| 4 | `baidu/ernie-5.5-flash-preview:free` | bianca × t-webhook | 4000, `reasoning.effort=low` | Cortado: 3810 tokens de raciocínio, sem JSON |
| 5 | `nvidia/nemotron-3.5-super-vl:free` | bianca × t-webhook | 8000 | Cortado: 6826 tokens de raciocínio, sem JSON |
| 6 | `baidu/ernie-5.5-flash-preview:free` | marta × t-2fa | 12000 | HTTP 429 do provedor após 0,9 s; sem resultado |

Os dois candidatos são modelos de raciocínio: parte de `max_tokens` é gasta "pensando" antes do JSON, e o gasto cresce com a complexidade do ticket. Com o limite anterior de 1500 tokens o modelo padrão não entrega nada.

## Opções consideradas

### Manter `baidu/ernie-5.5-flash-preview:free` com `LLM_MAX_TOKENS=8000`

- **Prós**: É o único candidato com saída completa e válida medida (chamada 2); a saída em português foi adequada ao perfil leigo; 8000 tokens foram aceitos pelo provedor.
- **Contras**: 25 s por geração no ticket simples; no ticket complexo (t-webhook) 8000 tokens não bastaram; um erro de grafia na saída.
- **Custo**: Zero em dinheiro; alto em latência e em cota de tokens gratuitos.
- **Risco**: Médio: tickets complexos podem falhar por corte, e a falha é registrada com a causa. Um limite maior (12000) não foi validado porque a chamada 6 recebeu 429.

### Trocar para `nvidia/nemotron-3.5-super-vl:free`

- **Prós**: Mesmo tipo de modelo e mesma gratuidade; gastou menos raciocínio que o outro candidato no mesmo ticket complexo (6826 tokens, contra 8000 do outro, que bateu no limite).
- **Contras**: Medido uma vez, só no ticket complexo, e também foi cortado; sem evidência de saída válida em português.
- **Custo**: Zero em dinheiro; o orçamento de chamadas reais da etapa se esgotou antes de uma segunda medição.
- **Risco**: Alto: nenhuma saída completa medida.

### Limitar o raciocínio com `reasoning.effort=low`

- **Prós**: Reduziria latência e consumo se funcionasse; é o parâmetro unificado do provedor.
- **Contras**: Na chamada 4 o raciocínio ainda consumiu 3810 de 4000 tokens e a resposta foi cortada, sem ganho mensurável.
- **Custo**: Uma opção de configuração e um parâmetro extra por requisição.
- **Risco**: Médio: comportamento varia por modelo e não há garantia no modelo padrão.

## Decisão

Manter `baidu/ernie-5.5-flash-preview:free` como padrão e subir o padrão de `LLM_MAX_TOKENS` de 1500 para 8000 (em `Settings` e `.env.example`). Não adotar o parâmetro de esforço de raciocínio. O adaptador passa a registrar `reasoning_tokens` no `usage` e a falhar de imediato, com a causa e o remédio, quando a resposta é cortada por `max_tokens` sem JSON aproveitável.

## Por que vence

- **O que ganha e o que perde**: Ganha o único caminho com saída completa medida e um erro acionável nos casos de corte. Perde latência baixa e a garantia de cobrir tickets complexos com o limite padrão.
- **Por que compensa**: Compensa porque a alternativa não tem nenhuma saída completa medida e o controle de raciocínio não mostrou efeito. Falhar cedo com mensagem clara evita gastar uma chamada de reparo que bateria no mesmo limite.

## Consequências

- Quem mantém um `.env` antigo com `LLM_MAX_TOKENS=1500` recebe `InvalidLLMOutput` com a instrução de aumentar o limite; o `.env.example` já traz 8000.
- Para tickets complexos pode ser preciso um limite maior que 8000; isso fica como ponto de medição da Etapa 5, junto da comparação v1 × v2, quando houver cota disponível.
- O provedor `fake` continua sendo o caminho para testes e demonstração sem custo.

## Como verificar

`.venv/bin/python scripts/smoke_llm.py --max-tokens 6000` repete a chamada 2 e imprime JSON válido, schema válido, latência, tokens de raciocínio e a razão de palavras em português; `var/smoke/calls.log` lista as chamadas reais feitas. Teste automatizado: resposta com `finish_reason=length` e conteúdo vazio vira `InvalidLLMOutput` citando `LLM_MAX_TOKENS` (`tests/test_llm_openai_compat.py`).
