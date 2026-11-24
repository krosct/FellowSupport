# ADR 0028 · Política de cache: ponteiro para a execução, acerto gravado e campos da chave

- **Status**: Aceito (complementa o [ADR 0010](0010-chave-de-cache.md) e o [ADR 0035](0035-cache-grava-sempre.md))
- **Data**: 2026-11-20

## Contexto

O ADR 0010 definiu a chave canônica e o acerto gravado como execução. Restava fechar três pontos estruturais do cache:
o que o arquivo de cache guarda, o que o registro de um acerto contém e quais campos adicionais entram na chave.
Além disso, o ADR 0027 criou o parâmetro `reasoning`, que muda a saída do modelo e por isso precisa integrar a chave.

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

### 3. Campos da chave

#### Os do ADR 0010 com `reasoning` e o hash dos arquivos do prompt (não o do `meta.json`)

- **Prós**: Trocar `LLM_REASONING` muda a saída e, portanto, a chave; qualquer alteração nos arquivos do prompt
  também invalida a chave (coberto por teste), em vez de devolver saída desatualizada.
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
- A `cache_key` vai em todo registro (inclusive no de erro e quando `use_cache` está desligado), para o histórico
  localizar execuções equivalentes. A política de consulta vs. gravação (`use_cache=false` pula apenas a leitura) está
  no ADR 0035.
- A chave inclui `reasoning`. Cada tipo do modo `all` consulta o cache sozinho.

## Por que vence

- **O que ganha e o que perde**: Ganha uma fonte única da saída e registros que dizem a verdade sobre custo e tempo.
  Perde a leitura em um arquivo só.
- **Por que compensa**: Compensa porque garante evidência confiável de que o cache evita chamadas equivalentes: se o
  registro de acerto herdasse números da chamada original, as somas de uso e latência ficariam distorcidas.

## Consequências

- Somas de `usage` e de `attempts` sobre o histórico refletem o gasto real: acertos contam zero.
- Para renovar uma entrada, basta gerar com `use_cache=false` / `--no-cache` (com confirmação, ADR 0036) ou mudar um
  insumo da chave.

## Como verificar

`tests/test_cache.py`: segunda geração com `FakeLLM` contador (uma chamada, `cache_hit: true`, `attempts: 0`),
invalidação por campo, erro fora do cache, ponteiro órfão curado e modo `all`. `tests/test_cache_key.py` cobre a chave;
`tests/test_storage_cache.py`, o armazenamento e a escrita atômica.
