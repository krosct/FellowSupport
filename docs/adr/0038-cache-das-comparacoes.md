# ADR 0038 · Cache das comparações e aba Comparar por execuções

- **Status**: Aceito (complementa os ADRs [0031](0031-arquivo-de-comparacao-e-vencedor.md) e [0035](0035-cache-grava-sempre.md))
- **Data**: 2026-11-23

## Contexto

Na comparação, o usuário escolhe para cada versão uma **execução que já existe** (a do cache de geração ou uma mais
antiga) e compara os resultados, sem disparar novas gerações. Nesse fluxo, o cache refere-se à **comparação**, não à
geração. Uma comparação já salva das mesmas execuções (`var/comparisons/<id>.json`, ADR 0031) é oferecida ao usuário em
vez de abrir uma avaliação nova sem aviso; a caixa "Usar cache" não se aplica à aba Comparar. Falta definir a
identidade de uma comparação para o cache e onde a busca roda.

## Opções consideradas

### 1. Identidade de uma comparação no cache

#### O conjunto de `run_id` das execuções comparadas, em qualquer ordem

- **Prós**: Exata: as saídas avaliadas são as mesmas; não confunde duas rodadas do mesmo cenário com saídas
  diferentes; não depende de hash novo nem de campo novo no arquivo (o `run_id` de cada versão já está nele).
- **Contras**: Comparar execuções diferentes das mesmas versões nunca acerta o cache, mesmo com cenário igual.
- **Custo**: Baixo (função pura no domínio, `covers_runs`).
- **Risco**: Baixo.

#### Cenário mais conjunto de versões (cliente, ticket, tipo e `prompt_version`)

- **Prós**: Acerta mais vezes.
- **Contras**: Mostraria notas dadas a outras saídas como se fossem destas; mistura execuções distintas.
- **Custo**: Baixo.
- **Risco**: Alto: resultado errado sem aviso.

### 2. Onde roda a busca

#### Endpoint `GET /api/comparisons/lookup?run_ids=...` sobre `ComparisonRepo.list_recent`

- **Prós**: A regra fica no serviço e no domínio, testável sem navegador e valendo para qualquer cliente; uma
  chamada só, sem baixar o detalhe de cada candidato; nenhuma porta nova (a listagem já existe); não chama o LLM.
- **Contras**: Lê todos os arquivos de comparação a cada pedido (como a listagem, ADR 0029); uma rota a mais, que
  precisa vir antes de `/comparisons/{id}`.
- **Custo**: Baixo a médio (serviço, rota, testes).
- **Risco**: Baixo para dezenas de comparações; passa a pesar com milhares (índice em arquivo seria o próximo passo).

#### Filtrar no navegador (listagem mais detalhe dos candidatos)

- **Prós**: Não muda a API.
- **Contras**: A regra de identidade vive no front; a listagem não traz os `run_id`, então são várias chamadas por
  clique; a CLI não reaproveita.
- **Custo**: Baixo.
- **Risco**: Médio: regras divergentes entre clientes.

## Decisão

- Domínio: `covers_runs(record, run_ids)` (mesmo conjunto de `run_id`). Serviço: `find_saved_comparison` valida como
  o salvamento (2 ou mais execuções distintas, senão 422) e devolve a mais recente que cobre as execuções, ou `None`.
- API: `GET /api/comparisons/lookup?run_ids=a&run_ids=b` devolve a comparação (`{ saved_path, comparison }`) ou
  `null`. Não gera nada e não conta no limite de taxa (não chama o LLM).
- Site (aba Comparar): mesmo molde da aba Gerar. Perfil e ticket à esquerda; à direita, o conteúdo, um seletor por
  versão ("Não comparar", depois as execuções da mais recente, a do cache de geração, à mais antiga) e Comparar. Sem
  caixa "Usar cache": ao comparar, o site consulta o `lookup`. Sem comparação salva, abre as execuções para avaliar e
  salvar. Com ela, uma janela oferece **Carregar comparação** (mostra em leitura, `SavedComparison`, com as notas dadas
  antes) e **Comparar novamente** (avaliação zerada, que ao salvar cria outro arquivo e não toca o anterior); Esc ou
  clique fora cancelam e mantêm a tela. "O que mudou" e a comparação ficam abaixo.
- Saídas em carrossel (`VersionCarousel`): duas colunas por vez (uma em tela estreita) e, com mais versões que isso,
  setas laterais que giram em ciclo infinito (v1, v2, v3, v1...), por clique ou por mouse parado sobre a seta (primeira
  troca após 0,6 s, depois uma por segundo; o clique suspende o avanço por mouse parado até o mouse sair). O giro é um
  deslize: a coluna que entra é montada fora da tela e a faixa se desloca uma posição com `transition` de 0,38 s; ao
  fim, a posição é confirmada sem remontar as colunas (chaves estáveis), então nada pisca. Cliques durante o deslize
  esperam a vez (até 2) e "reduzir movimento" troca sem animação. As notas ficam na página, então
  girar não as perde. Vale para a comparação nova e para a salva; o detalhe do Histórico continua com todas as colunas.

## Por que vence

- **O que ganha e o que perde**: Ganha uma regra de identidade exata, testável e única para qualquer cliente, sem
  gasto de cota. Perde acertos por semelhança de cenário e paga a leitura de todos os arquivos a cada consulta.
- **Por que compensa**: Reaproveitar notas de outras saídas daria um resultado errado sem aviso; a leitura é
  barata para o volume do projeto.

## Consequências

- Gerar versões novas passa a ser feito na aba Gerar (ou na CLI); a aba Comparar só lê execuções e comparações.
- Salvar a mesma comparação duas vezes cria dois arquivos; a busca devolve o mais novo.
- Execuções de cenários ou modelos diferentes continuam recusadas ao salvar (ADR 0021).

## Como verificar

- `.venv/bin/pytest -q tests/test_comparison.py tests/test_api_comparison.py` (testes `cache_da_comparacao` e `lookup`).
- No site: Comparar, escolher duas execuções que já têm comparação salva: aparece a janela "Já existe uma comparação".
  "Carregar comparação" mostra o selo "Comparação salva" e as notas antigas; "Comparar novamente" abre o formulário
  zerado. Com execuções sem comparação salva, o formulário abre direto.
