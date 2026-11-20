# ADR 0028 · Política de cache: ponteiro para a execução, acerto gravado e desligamento total

- **Status**: Aceito (complementa o ADR 0010)
- **Data**: 2026-11-20

## Contexto

O ADR 0010 definiu a chave canônica e o acerto gravado como execução. A implementação da Etapa 3 exigiu fechar
quatro pontos que ele deixou abertos: o que o arquivo de cache guarda, o que o registro de um acerto contém, o que
"desligar o cache" significa e o que entra na chave. Além disso, o ADR 0027 (posterior ao 0010) criou o parâmetro
`reasoning`, que muda a saída do modelo e por isso precisa estar na chave.

## Opções consideradas

### 1. Conteúdo do arquivo `var/cache/<sha256>.json`

#### Ponteiro `{cache_key, source_run_id, created_at}` para a execução de origem

- **Prós**: Uma só cópia da saída (a execução em `var/runs/`); nada para sincronizar; o cache é auditável, porque a
  origem é um registro completo (mensagens enviadas, tokens, modelo efetivo).
- **Contras**: Um acerto lê dois arquivos (ponteiro e origem); apagar a execução deixa o ponteiro órfão.
- **Custo**: Baixo (dois arquivos pequenos por acerto, ~0 ms medidos nos testes).
- **Risco**: Baixo: ponteiro órfão, ou apontando para registro de erro, vale como "não achei", a geração segue e,
  ao terminar com sucesso, regrava o ponteiro (o cache se cura sozinho; coberto por teste).

#### Cópia da saída dentro do arquivo de cache

- **Prós**: Um acerto lê um arquivo só; sobrevive à remoção da execução.
- **Contras**: Duas cópias da mesma saída, com risco de divergir; perde a ligação direta com os metadados da origem.
- **Custo**: Médio (duplicação de dados).
- **Risco**: Médio: divergência entre cache e histórico.

### 2. Registro de um acerto de cache

#### Nova execução com `cache_hit: true`, `source_run_id`, `attempts: 0`, `usage: {}` e latência medida

- **Prós**: Cada reaproveitamento fica auditável e aparece no histórico; `attempts: 0` e `usage: {}` dizem a verdade
  (nenhuma chamada, nenhum token gasto agora), o que mantém somas de custo corretas; a latência é o tempo real de
  ler o cache.
- **Contras**: Quem soma `attempts` ou lê `usage` precisa saber que um acerto vale zero; o histórico cresce a cada
  acerto.
- **Custo**: Baixo.
- **Risco**: Baixo.

#### Copiar `attempts`, `usage` e latência da origem

- **Prós**: Registro "completo" sem tratamento especial.
- **Contras**: Mostra "Reparado" e tokens que não foram gastos agora; latência de 25 s num acerto instantâneo,
  contradizendo a evidência que o cache deve dar.
- **Custo**: Baixo.
- **Risco**: Alto: o registro mentiria sobre custo e tempo.

### 3. Significado de desligar o cache (`CACHE_ENABLED=false`, `use_cache=false`, `--no-cache`)

#### Não ler **nem gravar**

- **Prós**: Comportamento previsível ("sem cache" é sem cache); permite medir a latência real do modelo sem alterar
  o estado do cache; um teste simples verifica (a pasta de cache não é criada).
- **Contras**: Não dá para "atualizar" o cache com uma geração nova forçada; a entrada antiga permanece.
- **Custo**: Zero.
- **Risco**: Baixo.

#### Não ler, mas gravar (regerar e substituir)

- **Prós**: Permite renovar uma entrada que se quer trocar.
- **Contras**: O interruptor "desligar" passa a ter efeito colateral; depois de um experimento sem cache, as
  próximas chamadas passam a devolver o resultado do experimento.
- **Custo**: Baixo.
- **Risco**: Médio: surpresa para quem esperava um desligamento completo.

### 4. Campos da chave

#### Os do ADR 0010 mais `reasoning` e o hash do prompt dos arquivos (não o do `meta.json`)

- **Prós**: Trocar `LLM_REASONING` muda a saída e, portanto, a chave; editar um prompt sem criar versão nova também
  invalida (coberto por teste), em vez de devolver saída desatualizada.
- **Contras**: Qualquer ajuste de parâmetro cria uma entrada nova; sem TTL, a entrada vale para sempre.
- **Custo**: Baixo.
- **Risco**: Baixo.

#### Os campos do ADR 0010 sem `reasoning`

- **Prós**: Chave um pouco mais estável.
- **Contras**: Com `reasoning` diferente o cache devolveria saída gerada com outra configuração, invalidando
  comparações.
- **Custo**: Baixo.
- **Risco**: Alto.

## Decisão

- O arquivo de cache é um ponteiro para a execução de origem e só nasce depois de a execução estar gravada.
- Um acerto grava uma nova execução com `cache_hit: true`, `source_run_id`, `attempts: 0`, `usage: {}`, latência
  medida e `model_used` herdado da origem. Execuções com erro nunca entram no cache.
- Cache desligado (por configuração ou por chamada) não lê nem grava. A `cache_key` vai no registro de qualquer
  forma, inclusive no de erro, para o histórico localizar execuções equivalentes.
- A chave inclui `reasoning`. Cada tipo do modo `all` consulta o cache sozinho.

## Por que vence

- **O que ganha e o que perde**: Ganha uma fonte única da saída, registros que dizem a verdade sobre custo e tempo e
  um interruptor previsível. Perde a renovação forçada de uma entrada e a leitura em um arquivo só.
- **Por que compensa**: Compensa porque o PDF pede evidência de que o cache evita chamadas equivalentes, e essa
  evidência só é confiável se o registro do acerto não herdar números da chamada original.

## Consequências

- Somas de `usage` e de `attempts` sobre o histórico refletem o gasto real: acertos contam zero.
- Para renovar uma entrada, basta apagar `var/cache/<chave>.json` ou mudar um insumo da chave.
- Chaves antigas (anteriores a esta etapa) não existem: nenhuma execução anterior tem `cache_key`, então nada é
  reaproveitado delas.

## Como verificar

`tests/test_cache.py`: segunda geração com `FakeLLM` contador (uma chamada, `cache_hit: true`, `attempts: 0`),
invalidação por campo, `use_cache=false` sem criar `var/cache/`, erro fora do cache, ponteiro órfão curado e modo
`all`. `tests/test_cache_key.py` cobre a chave; `tests/test_storage_cache.py`, o armazenamento e a escrita atômica.
