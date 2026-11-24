# ADR 0035 · Cache: gravar sempre e ler só quando pedido

- **Status**: Aceito (complementa os ADRs [0010](0010-chave-de-cache.md) e [0028](0028-politica-de-cache.md))
- **Data**: 2026-11-23

## Contexto

Uma geração feita com a consulta ao cache desligada (`use_cache=false`, `--no-cache`, caixa "Usar cache" desmarcada)
deve gerar uma nova saída sem reaproveitar entradas antigas, mas precisa atualizar o ponteiro de `var/cache/<chave>.json`
para que consultas futuras devolvam a geração mais recente da chave. Um cache convencional separa leitura e gravação:
toda geração bem-sucedida é guardada, e a consulta antes de gerar é opcional, sem precisar de um interruptor global
separado no servidor (`CACHE_ENABLED`).

## Opções consideradas

### 1. Significado de desligar o cache

#### Não ler, mas gravar (a opção é só sobre a consulta)

- **Prós**: Regra única e previsível ("o que foi gerado fica guardado"); o ponteiro sempre aponta para a última
  geração real da chave; gerar com a caixa desmarcada é também a forma de renovar uma entrada.
- **Contras**: Uma geração feita "só para ver" passa a ser o que as próximas consultas devolvem; não há um modo que
  gere sem atualizar o ponteiro da chave.
- **Custo**: Baixo (um ramo condicional apenas na leitura).
- **Risco**: Baixo a médio: a saída devolvida por um acerto continua rastreável por `source_run_id`.

#### Não ler e não gravar

- **Prós**: O desligamento não tem efeito colateral; a pasta de cache não é criada quando desligado.
- **Contras**: Gerações feitas com a caixa desmarcada ficam fora do cache; o ponteiro pode apontar para uma geração
  mais antiga que outra equivalente; não há como renovar uma entrada sem apagar o arquivo.
- **Custo**: Baixo.
- **Risco**: Médio: comportamento diferente do esperado de um cache, gerando dúvida sobre qual geração entra em
  comparações futuras.

### 2. Interruptor de servidor `CACHE_ENABLED`

#### Não manter interruptor global de servidor

- **Prós**: Sem estado "desligado no servidor"; a caixa do site e a flag da CLI ficam sem duas camadas com sentidos
  diferentes; `GET /api/meta` não precisa expor esse estado.
- **Contras**: Não há um jeito de operar sem gravar o ponteiro em disco (ex.: sistema de arquivos somente leitura).
- **Custo**: Baixo.
- **Risco**: Baixo: `.env` antigo com `CACHE_ENABLED` é ignorado (`extra="ignore"`).

#### Manter interruptor mestre no servidor (não lê nem grava)

- **Prós**: Saída de emergência operacional.
- **Contras**: Reintroduz ambiguidade: a variável cortaria a gravação e a caixa não.
- **Custo**: Baixo.
- **Risco**: Médio: o comportamento passa a depender de uma configuração invisível ao usuário do site.

## Decisão

- `use_cache` (caixa, `--no-cache`, API) decide só se o cache é **consultado** antes de gerar.
- Toda geração bem-sucedida que chamou o LLM grava o ponteiro da sua chave, com `use_cache` ligado ou não. Erros
  nunca entram. Um acerto não regrava o ponteiro, que segue na origem.
- Vale para o cache das gerações (`var/cache/`).
- Não há interruptor global `CACHE_ENABLED`.

## Por que vence

- **O que ganha e o que perde**: Ganha um cache que guarda tudo o que foi gerado e cuja origem é sempre a última
  geração da chave. Perde o modo "medir sem tocar no cache" e o interruptor de servidor.
- **Por que compensa**: O comportamento é o de um cache convencional, e quem precisa de uma geração nova sem consultar
  o cache continua tendo `use_cache=false`, agora com o efeito de atualizar a entrada.

## Consequências

- Duas gerações da mesma chave: a consulta seguinte devolve a mais recente que chamou o LLM.
- Execuções anteriores a este ADR feitas sem cache não ganham ponteiro retroativo.
- A substituição de uma entrada existente exige confirmação (ADR 0036).
- `tests/test_cache.py` cobre a gravação com `use_cache=false` e a origem na última geração.
