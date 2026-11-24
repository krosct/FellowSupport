# ADR 0027 · Controle de raciocínio dos modelos gratuitos

- **Status**: Aceito
- **Data**: 2026-11-20

## Contexto

O ADR 0026 mediu que os modelos `:free` do OpenRouter são de raciocínio: o modelo padrão (`baidu/ernie-5.5-flash-preview:free`) gasta de 4 mil a 8 mil tokens pensando antes do JSON, e `reasoning.effort=low` não reduziu o consumo. Esta etapa testou se o parâmetro `reasoning` do OpenRouter desliga o raciocínio, para cortar tokens e latência mantendo o JSON válido.

A documentação do provedor descreve `reasoning.effort` (`none` desliga) e `reasoning.enabled` (`false` desliga), mas ressalva que modelos de raciocínio obrigatório não aceitam desligar. O catálogo público (`GET /api/v1/models`, sem custo) informa isso por modelo:

| Modelo | `reasoning.mandatory` | Esforços aceitos |
|---|---|---|
| `baidu/ernie-5.5-flash-preview:free` | verdadeiro | só `high` |
| `nvidia/nemotron-3.5-super-vl:free` | falso | não informado |

Medições (3 chamadas reais `:free`, prompt `v1`, diagnóstico, `marta` × `t-2fa`, `max_tokens` 8000, modo `json_schema`, sem retentativas do SDK):

| # | Modelo | `reasoning` enviado | Resultado |
|---|---|---|---|
| 1 | `baidu/ernie-5.5-flash-preview:free` | `{"enabled": false}` | HTTP 400: "Reasoning is mandatory for this endpoint and cannot be disabled." |
| 2 | `baidu/ernie-5.5-flash-preview:free` | `{"effort": "none"}` | HTTP 400, a mesma mensagem |
| 3 | `nvidia/nemotron-3.5-super-vl:free` | `{"enabled": false}` | JSON e schema válidos em 9,7 s; 958 tokens de saída, sem tokens de raciocínio; 476 palavras, 99,5% das palavras funcionais reconhecidas em português |

Para comparar: no mesmo cenário, o modelo padrão com raciocínio ligado levou 25,4 s e 5240 tokens de saída, 3833 deles de raciocínio (ADR 0026, chamada 2). A chamada 3 é uma única amostra de um cenário simples; o ticket complexo (`t-webhook`) não foi repetido com raciocínio desligado.

Quatro chamadas reais adicionais, pela CLI `generate` (pipeline completo, `marta` × `t-2fa`), mostram o efeito do raciocínio nos novos tipos de conteúdo:

| # | Tipo | Modelo e raciocínio | `max_tokens` | Resultado |
|---|---|---|---|---|
| 4 | `flow_summary` | ernie, padrão | 1500 | Cortado: 1504 tokens, todos de raciocínio, sem JSON (9,3 s) |
| 5 | `flow_summary` | ernie, padrão | 8000 | Válido de primeira, 21,5 s; 4946 tokens de saída, 4459 de raciocínio; 10 nós e 9 arestas |
| 6 | `resolution_steps` | ernie, padrão | 8000 | Cortado: 8000 tokens, todos de raciocínio, sem JSON (41,7 s) |
| 7 | `resolution_steps` | nemotron, `off` | 8000 | Válido de primeira, 4,8 s; 5 passos, sem markdown (canal telefone) |

O raciocínio do modelo padrão cresce com a tarefa: o passo a passo, que pede mais campos por item, esgotou 8000 tokens no cenário simples em que o fluxograma coube.

## Opções consideradas

### Expor `LLM_REASONING` (`default`, `off`, `none`, `low`, `medium`, `high`) com padrão `default`

- **Prós**: Permite desligar o raciocínio em modelos que o aceitam (chamada 3: 9,7 s contra 25,4 s e cerca de 5 vezes menos tokens); o padrão `default` não envia o parâmetro e preserva o comportamento do modelo padrão; o valor entra no registro da execução (`params.reasoning`), então comparações recusam modelos ou configurações diferentes.
- **Contras**: O parâmetro é do OpenRouter e outros provedores compatíveis podem recusá-lo; o modelo padrão não se beneficia (chamadas 1 e 2).
- **Custo**: Baixo: um campo de configuração, um campo no `LLMParams` e no registro, e `extra_body` na requisição.
- **Risco**: Baixo: valor incompatível com o modelo vira `LLMUnavailable` com a causa do provedor (HTTP 400 com a mensagem), sem efeito colateral.

### Padrão `off`

- **Prós**: Reduziria latência e tokens nos modelos que aceitam.
- **Contras**: Quebra o modelo padrão atual: as chamadas 1 e 2 mostram HTTP 400 em toda geração.
- **Custo**: Baixo.
- **Risco**: Alto: o projeto deixaria de gerar com a configuração padrão.

### Não expor o parâmetro

- **Prós**: Menos configuração e nenhum acoplamento ao OpenRouter.
- **Contras**: Descarta o ganho medido em modelos de raciocínio opcional e obriga a editar código para testá-lo.
- **Custo**: Zero.
- **Risco**: Baixo, com custo de oportunidade.

### Trocar o modelo padrão por `nvidia/nemotron-3.5-super-vl:free` com `LLM_REASONING=off`

- **Prós**: Única combinação medida que entrega JSON válido em português em menos de 10 s e com menos de mil tokens.
- **Contras**: Uma só amostra, só no cenário simples; sem medição no ticket complexo nem repetição para variância; a escolha do modelo padrão foi decidida no ADR 0026.
- **Custo**: Baixo para trocar, mas exige novas medições para sustentar a troca.
- **Risco**: Médio: a evidência é insuficiente para generalizar.

## Decisão

Expor `LLM_REASONING` em `Settings` e `.env.example` com padrão `default`, enviado ao provedor como `extra_body={"reasoning": {...}}` (`off` vira `{"enabled": false}`, `none` vira `{"effort": "none"}` e os demais viram `{"effort": <valor>}`) e gravado em `params.reasoning`. O modelo padrão não muda.

## Por que vence

- **O que ganha e o que perde**: Ganha um controle verificado, útil com modelos de raciocínio opcional, sem risco para o padrão. Perde nada no modelo padrão, que continua com raciocínio obrigatório e latência alta.
- **Por que compensa**: O padrão `default` é o único valor que funciona no modelo padrão; `off` só ajuda quando se muda o modelo. Documentar a evidência do `nemotron` com a ressalva de amostra única deixa a decisão do modelo para uma medição maior.

## Consequências

- O modelo padrão segue gastando milhares de tokens com raciocínio; `LLM_MAX_TOKENS=12000` (ADR 0026) dá folga para respostas que precisam de mais tokens, como o passo a passo.
- Quem usar outro modelo pode testar com `LLM_REASONING=off`; se o provedor recusar, a mensagem de erro traz a causa.
- A troca eventual do modelo padrão depende de medições comparáveis cobrindo todos os tipos de conteúdo e tickets.

## Como verificar

`.venv/bin/python -m scripts.smoke_llm --reasoning off` (uma chamada real; `var/smoke/calls.log` registra `reasoning=off`). Testes: `tests/test_llm_openai_compat.py` (corpo da requisição por modo, ausência do parâmetro no `default` e recusa do provedor) e `tests/test_generators.py` (`params.reasoning` no registro).
