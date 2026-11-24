# ADR 0006 · Versões de prompt imutáveis com hash de conteúdo

- **Status**: Aceito
- **Data**: 2026-11-20

## Contexto

A comparação entre versões só é válida se cada versão for estável. Editar um prompt no lugar invalida resultados e caches anteriores sem aviso.

## Opções consideradas

### Versão imutável com `content_sha256` no `meta.json` e teste de comparação do hash

- **Prós**: Qualquer edição sem nova versão quebra o teste; cache e comparações permanecem corretos.
- **Contras**: Mais pastas; correções pequenas exigem nova versão.
- **Custo**: Baixo.
- **Risco**: Baixo: o custo é só processo.

### Editar a versão no lugar

- **Prós**: Menos arquivos.
- **Contras**: Resultados antigos deixam de corresponder ao prompt registrado; comparação perde valor.
- **Custo**: Baixo.
- **Risco**: Alto: erro silencioso.

### Versão derivada só do commit git

- **Prós**: Sem manutenção manual do hash.
- **Contras**: Acopla a identidade do prompt ao histórico git; execuções locais com alterações não commitadas ficam sem identificação confiável.
- **Custo**: Médio.
- **Risco**: Médio: identificação ambígua.

## Decisão

Cada pasta de versão é imutável; o `meta.json` guarda o SHA-256 dos arquivos e um teste compara com o conteúdo real.

## Por que vence

- **O que ganha e o que perde**: Ganha rastreabilidade confiável das comparações. Perde a possibilidade de ajustar uma versão no lugar.
- **Por que compensa**: Compensa porque comparar versões exige garantir que cada identificador de prompt corresponda exatamente ao mesmo texto em todas as execuções e análises.

## Consequências

O `prompt_sha256` entra no registro de execução e na chave de cache (ADR 0010).

## Como verificar

Teste de imutabilidade que falha ao alterar um byte de qualquer arquivo de prompt sem atualizar o `meta.json`.
