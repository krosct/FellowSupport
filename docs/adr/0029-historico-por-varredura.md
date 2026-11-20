# ADR 0029 · Histórico por varredura preguiçosa dos arquivos de execução

- **Status**: Aceito
- **Data**: 2026-11-20

## Contexto

O PDF (4.4) pede para localizar execuções equivalentes e o plano pede histórico na API, na CLI e no site, com filtros
por cliente, ticket, tipo, versão e status. O ADR 0009 aceitou "listar o histórico exige varrer a pasta" como custo
do formato de um arquivo JSON por execução. Falta decidir como varrer, onde ficam os filtros e o que a listagem
devolve.

## Opções consideradas

### Varredura preguiçosa do mais novo para o mais antigo, filtros e limite no serviço `history`

- **Prós**: Sem estado extra para manter consistente; o limite interrompe a leitura (o histórico de 50 itens abre 50
  arquivos se não houver filtro); API, CLI e site aplicam as mesmas regras porque o filtro vive num só lugar; a pasta
  continua sendo a única fonte da verdade.
- **Contras**: Custo proporcional ao número de arquivos quando o filtro é raro (precisa ler vários até achar `limit`);
  cada listagem reabre os arquivos.
- **Custo**: Baixo: um `glob`, um `stat` por arquivo para ordenar e a leitura só do necessário.
- **Risco**: Baixo nesta escala (centenas de execuções); cresce linearmente com milhares.

### Arquivo de índice (`index.json`) atualizado a cada execução

- **Prós**: Listagem sem abrir os registros.
- **Contras**: Segundo arquivo para manter consistente com a pasta (execuções apagadas à mão, escrita concorrente do
  índice no modo `all`); reintroduz o ponto único de corrupção que o ADR 0009 evitou.
- **Custo**: Médio.
- **Risco**: Médio: índice divergente do que existe em disco.

### SQLite

- **Prós**: Consultas e índices de verdade.
- **Contras**: O PDF pede JSON e a evidência da entrega são os arquivos; migrações e dependência de esquema.
- **Custo**: Médio a alto.
- **Risco**: Médio: desvia do requisito.

### Listagem devolvendo o registro completo

- **Prós**: Um só formato para lista e detalhe.
- **Contras**: Cada registro tem a saída e as mensagens enviadas ao modelo (dezenas de KB); 50 itens pesam
  centenas de KB para desenhar uma tabela.
- **Custo**: Médio (tráfego e memória).
- **Risco**: Baixo, mas desperdício evitável: a API devolve um resumo (`RunSummaryOut`) e o registro completo só em
  `GET /api/runs/{id}`.

## Decisão

- `RunRepo.iter_recent()` percorre os arquivos do mais recente para o mais antigo (carimbo do nome do arquivo, com
  `mtime` como desempate no mesmo segundo) e lê um por vez; arquivo ilegível é pulado com registro em log.
- `services/history.py` aplica filtros por igualdade (cliente, ticket, tipo, versão, status), o filtro por
  `cache_key` e o limite (padrão 50, máximo 500, valor fora da faixa é `ValidationFailed`).
- O filtro por `cache_key` casa por prefixo: a CLI mostra só o começo da chave e copiá-lo basta para listar as
  execuções equivalentes, inclusive as que terminaram em erro ou rodaram sem cache.
- O id de execução só entra num `glob` depois de validado contra `[0-9a-f]{12}`.

## Por que vence

- **O que ganha e o que perde**: Ganha simplicidade, uma fonte da verdade e regras iguais em todas as entradas.
  Perde desempenho de consulta em volumes grandes, que o escopo não tem.
- **Por que compensa**: Compensa porque o ADR 0009 já aceitou esse custo ao escolher arquivos por execução, e um
  índice ou banco trocaria um custo irrelevante por um risco de inconsistência.

## Consequências

- Se o volume crescer, o ponto de troca é um índice ou SQLite atrás da mesma porta `RunRepo`, sem mudar o serviço.
- Execuções gravadas antes da Etapa 3 não têm `cache_key`: aparecem na lista, mas nunca casam com o filtro por chave.

## Como verificar

`tests/test_history.py` (ordem, cada filtro, prefixo de chave, limite e faixa inválida, API com 422 e 404, CLI) e
`tests/test_storage_runs.py` (ordem por carimbo e `mtime`, id malformado, arquivo corrompido).
