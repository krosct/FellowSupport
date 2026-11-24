# ADR 0031 · Arquivo de comparação, vencedor e empate

- **Status**: Aceito (complementa os ADRs 0020 e 0021)
- **Data**: 2026-11-20

## Contexto

O projeto exige que a comparação entre versões registre os resultados comparados e a avaliação comparativa em JSON junto das notas usadas. Os ADRs 0020 e 0021 definiram a rubrica e a
justiça, mas não o formato do arquivo da comparação, como se decide o vencedor nem o que fazer num empate.

## Opções consideradas

### 1. Formato e local do arquivo

#### `var/comparisons/<id>.json` com cenário, execuções (id, caminho e cópia da saída), avaliação e total por versão, vencedor e conclusão

- **Prós**: um arquivo autossuficiente, legível no histórico sem abrir cada execução em `var/runs/`; o cenário aparece uma
  vez (a justiça garante que é comum); o id no nome torna o caminho previsível.
- **Contras**: a saída é duplicada (também está em `var/runs/`); a cópia pode divergir se a execução for editada à mão.
- **Custo**: Baixo (alguns KB por comparação).
- **Risco**: Baixo: as execuções não são editadas pelo sistema depois de salvas, exceto para gravar avaliações.

#### Só os ids das execuções, sem cópia das saídas

- **Prós**: sem duplicação.
- **Contras**: cada leitura da comparação exigiria abrir todos os arquivos referenciados em `var/runs/` e falharia se uma execução antiga fosse apagada.
- **Custo**: Baixo.
- **Risco**: Médio: dependência frágil de múltiplos arquivos para exibir comparações antigas.

### 2. Critério de vencedor

#### Maior soma das notas do candidato; empate no topo não tem vencedor (`winner: null`)

- **Prós**: simples e auditável; só a nota do candidato conta; não esconde empates.
- **Contras**: a soma dá o mesmo peso aos três critérios e pode mascarar um critério muito pior; com poucas notas
  inteiras os empates são frequentes.
- **Custo**: Zero.
- **Risco**: Baixo: a conclusão escrita pelo candidato pode explicar a preferência.

#### Desempate por critério (por exemplo, o de maior `customer_fit`)

- **Prós**: sempre há vencedor.
- **Contras**: escolher o critério de desempate é arbitrário e esconde um empate que também é resultado.
- **Custo**: Baixo.
- **Risco**: Médio: conclusão aparentemente mais forte do que a evidência.

#### Média ponderada dos critérios

- **Prós**: permite priorizar `customer_fit` (a hipótese da v2).
- **Contras**: o projeto não define pesos distintos entre critérios; escolhê-los depois de ver os resultados enviesaria a conclusão.
- **Custo**: Médio.
- **Risco**: Alto: peso ajustado a posteriori.

### 3. Conclusão

#### Texto do candidato (opcional); sem ele, resumo automático dos totais, com a origem gravada em `conclusion_source`

- **Prós**: preserva a interpretação escrita pelo avaliador humano; o resumo automático evita arquivo sem conclusão e é
  marcado como automático.
- **Contras**: dois tipos de texto no mesmo campo.
- **Custo**: Baixo.
- **Risco**: Baixo: `conclusion_source` evita confundir um com o outro.

## Decisão

Arquivo `var/comparisons/<id>.json` (id de 12 hexadecimais) com `scenario`, `versions[]` (`prompt_version`, `run_id`,
`run_path`, `prompt_sha256`, `cache_hit`, `output`, `rendered`, `evaluation`, `total`), `winner`,
`conclusion` e `conclusion_source`. O total de cada versão é a soma das três notas do candidato (3 a 15). O vencedor é
a versão de maior total; empate no topo grava `winner: null`. A comparação só é salva com as versões diferentes entre
si, as execuções justas (ADR 0021) e a avaliação completa de cada lado; as notas enviadas são validadas antes de
qualquer escrita.

## Por que vence

- **O que ganha e o que perde**: ganha evidência autossuficiente e um critério de vencedor sem escolhas arbitrárias.
  Perde a unicidade do resultado (empates possíveis) e a pequena duplicação das saídas.
- **Por que compensa**: um empate honesto vale mais que um vencedor obtido por um desempate escolhido depois dos
  resultados, e a cópia das saídas garante que cada comparação em `var/comparisons/` seja legível de forma independente.

## Consequências

- Listar comparações lê todos os arquivos de `var/comparisons/` (poucos) e ordena por `created_at`.
- Reavaliar uma execução depois de salva a comparação não altera o arquivo já gravado: salvar de novo cria outra
  comparação.

## Como verificar

`tests/test_comparison.py`: cenário, ids, avaliações, totais, vencedor, empate (inclusive entre três versões), conclusão
do candidato e automática, recusa de avaliação incompleta sem gravar nada, listagem,
abertura por id e arquivo ilegível ignorado.
