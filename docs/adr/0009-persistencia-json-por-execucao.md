# ADR 0009 · Persistência em JSON, um arquivo por execução

- **Status**: Aceito
- **Data**: 2026-11-20

## Contexto

O PDF exige salvar cada execução em JSON com data/hora, localizar execuções equivalentes e indicar onde o JSON foi salvo.

## Opções consideradas

### Um arquivo por execução em `var/runs/AAAA-MM-DD/<ts>_<id>.json`, escrita atômica, comparações em `var/comparisons/` e cache em `var/cache/<sha256>.json`

- **Prós**: O caminho do arquivo responde diretamente a "onde o JSON foi salvo"; sem corrupção por escrita concorrente; fácil de inspecionar e versionar amostras.
- **Contras**: Listar o histórico exige varrer a pasta; muitos arquivos com o tempo.
- **Custo**: Baixo.
- **Risco**: Baixo: escrita atômica (arquivo temporário e `os.replace`) evita arquivos parciais.

### Um único `history.json`

- **Prós**: Um arquivo só, leitura simples.
- **Contras**: Reescrita total a cada execução; corrupção possível com escritas concorrentes; cresce sem limite.
- **Custo**: Baixo.
- **Risco**: Médio a alto: perda de histórico.

### SQLite

- **Prós**: Consultas, índices e transações.
- **Contras**: O PDF pede JSON; adiciona esquema e migrações; saída menos inspecionável.
- **Custo**: Médio.
- **Risco**: Médio: desvia do requisito.

## Decisão

Um arquivo JSON por execução, escrita atômica via helper único, diretórios por data e pastas separadas para comparações e cache.

## Por que vence

- **O que ganha e o que perde**: Ganha robustez, inspeção simples e aderência ao PDF. Perde consultas eficientes em grande volume, irrelevante nesta escala.
- **Por que compensa**: Compensa porque a escala é pequena e a evidência da entrega são justamente os arquivos JSON.

## Consequências

O helper de escrita atômica fica em `adapters/storage/json_files.py` e é a única forma de gravar.

## Como verificar

Teste do helper: o arquivo final existe, não restam temporários, e uma falha no meio não deixa arquivo parcial.
