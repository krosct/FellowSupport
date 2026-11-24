# ADR 0026 · Modelo padrão de geração e limite de tokens

- **Status**: Aceito (complementado pelo [ADR 0042](0042-corte-por-limite-decidido-no-servico.md) no tratamento de corte)
- **Data**: 2026-11-20

## Contexto

O modelo padrão precisa ser gratuito (`:free`), entregar JSON que valide contra o schema `Diagnosis` e escrever em português do Brasil. A medição inicial testou dois candidatos com `scripts/smoke_llm.py` (uma chamada por execução, sem reparo, sem retentativas do SDK) e com a CLI real, usando o prompt `v1`, temperatura 0,1 e o modo `json_schema`.

Medições iniciais:

| # | Modelo | Cenário | `max_tokens` | Resultado |
|---|---|---|---|---|
| 1 | `baidu/ernie-5.5-flash-preview:free` | marta × t-2fa | 1500 | Conteúdo vazio, `finish_reason=length`, 1500 tokens consumidos (10,1 s) |
| 2 | `baidu/ernie-5.5-flash-preview:free` | marta × t-2fa | 6000 | JSON válido, schema válido, 25,4 s, 5240 tokens de saída (3833 de raciocínio); 702 palavras, 98,7% das palavras funcionais reconhecidas em português; 4 hipóteses e 5 informações faltantes; um erro de grafia ("autentikador") |
| 3 | `baidu/ernie-5.5-flash-preview:free` | bianca × t-webhook | 8000 | Cortado: 8000 tokens, todos de raciocínio, sem JSON (37,3 s) |
| 4 | `baidu/ernie-5.5-flash-preview:free` | bianca × t-webhook | 4000, `reasoning.effort=low` | Cortado: 3810 tokens de raciocínio, sem JSON |
| 5 | `nvidia/nemotron-3.5-super-vl:free` | bianca × t-webhook | 8000 | Cortado: 6826 tokens de raciocínio, sem JSON |
| 6 | `baidu/ernie-5.5-flash-preview:free` | marta × t-2fa | 12000 | HTTP 429 do provedor após 0,9 s; sem resultado |

Os dois candidatos são modelos de raciocínio: parte de `max_tokens` é gasta "pensando" antes do JSON, e o gasto cresce com a complexidade do ticket. Com limites baixos (1500 ou 8000 em cenários complexos), o modelo padrão corta a resposta antes de concluir o JSON.

## Opções consideradas

### Manter `baidu/ernie-5.5-flash-preview:free` com `LLM_MAX_TOKENS=12000`

- **Prós**: É o candidato com saída completa e válida medida em português adequado ao perfil leigo (chamada 2); 12000 tokens dão folga maior para raciocínio antes do JSON nos tickets complexos.
- **Contras**: Latência alta (25 s ou mais por geração) e consumo elevado de cota de tokens gratuitos; ainda sujeito a cortes impostos pelo provedor.
- **Custo**: Zero em dinheiro; alto em latência e em cota de tokens gratuitos.
- **Risco**: Médio: se algum provedor roteado cortar antes do limite configurado, a falha é registrada com o gasto e o provedor (ADR 0042).

### Trocar para `nvidia/nemotron-3.5-super-vl:free`

- **Prós**: Mesmo tipo de modelo e mesma gratuidade; gastou menos raciocínio que o outro candidato no mesmo ticket complexo (6826 tokens, contra 8000 do outro, que bateu no limite).
- **Contras**: Medido na seleção inicial uma única vez no ticket complexo e também foi cortado com raciocínio ligado; sem evidência inicial suficiente para substituir o padrão global.
- **Custo**: Zero em dinheiro.
- **Risco**: Alto como padrão único sem desligar raciocínio (tratado no ADR 0027 e no ADR 0032).

### Limitar o raciocínio com `reasoning.effort=low`

- **Prós**: Reduziria latência e consumo se funcionasse; é o parâmetro unificado do provedor.
- **Contras**: Na chamada 4 o raciocínio ainda consumiu 3810 de 4000 tokens e a resposta foi cortada, sem ganho mensurável.
- **Custo**: Uma opção de configuração e um parâmetro extra por requisição.
- **Risco**: Médio: comportamento varia por modelo e o modelo padrão não aceita desligar o raciocínio (ADR 0027).

## Decisão

Manter `baidu/ernie-5.5-flash-preview:free` como padrão e definir o padrão de `LLM_MAX_TOKENS` em `12000` (em `Settings` e `.env.example`). O adaptador registra `reasoning_tokens` no `usage` e devolve `finish_reason`, `provider_used` e `response_id` para que o serviço decida a falha por corte sem reparo (ADR 0042).

## Por que vence

- **O que ganha e o que perde**: Ganha folga de tokens para cenários complexos e diagnóstico completo nos casos de corte. Perde latência baixa no modelo padrão.
- **Por que compensa**: Compensa porque modelos gratuitos de raciocínio obrigatório precisam de folga de `max_tokens` para não retornar conteúdo vazio, e falhar cedo sem reparo quando há corte sem JSON evita gastar uma segunda chamada que bateria no mesmo limite.

## Consequências

- `Settings` e `.env.example` trazem `LLM_MAX_TOKENS=12000`; valores menores no `.env` podem provocar corte em tickets complexos, tratado pelo serviço com mensagem orientativa (ADR 0042).
- O provedor `fake` continua sendo o caminho para testes e demonstração sem custo.

## Como verificar

`.venv/bin/python -m scripts.smoke_llm --max-tokens 6000` repete a chamada 2 e imprime JSON válido, schema válido, latência, tokens de raciocínio e a razão de palavras em português. Testes automatizados: `tests/test_config.py` confere o modelo padrão entre `Settings` e `.env.example`; `tests/test_llm_openai_compat.py` e `tests/test_observability.py` cobrem `reasoning_tokens` e o tratamento de corte por `finish_reason=length`.
