# ADR 0030 · Número aposentado

- **Status**: Aposentado
- **Data**: 2026-11-23

## Contexto

A decisão originalmente registrada sob o número `0030` deixou de existir no projeto e foi removida dos ADRs e da documentação. Como as decisões posteriores (`0031` a `0043`) já são referenciadas no código, nos testes, nos arquivos de configuração e no histórico de commits, foi preciso definir como tratar a lacuna entre `0029` e `0031`.

## Opções consideradas

### Aposentar o número `0030` e preservar `0031`..`0043` (escolhida)

- **Prós**: Mantém estáveis todas as referências a `ADR 0031`..`ADR 0043` no código, nos testes, na documentação e no histórico de commits; evita reutilizar um identificador que já pertenceu a outro registro.
- **Contras**: Mantém um registro marcador sem decisão técnica ativa na sequência numérica.
- **Custo**: Mínimo: um arquivo marcador e uma linha no índice.
- **Risco**: Baixo: o status `Aposentado` deixa explícito que o número não está ausente por erro.

### Renumerar `0031`..`0043` para `0030`..`0042`

- **Prós**: Sequência contínua sem marcadores aposentados.
- **Contras**: Exige alterar dezenas de referências cruzadas em código, testes e documentos e cria divergência com mensagens de commits anteriores.
- **Custo**: Médio.
- **Risco**: Médio: risco de inconsistência entre referências e histórico do repositório.

## Decisão

Aposentar o número `0030` com este registro marcador, mantendo inalterada a numeração `0031`..`0043` dos demais ADRs.

## Por que vence

- **O que ganha e o que perde**: Ganha estabilidade de identificadores em toda a base de código e documentação. Perde apenas a existência de uma decisão ativa no número `0030`.
- **Por que compensa**: Identificadores de ADR são estáveis após referenciados; preservar o número como aposentado documenta o motivo da lacuna com custo mínimo e risco nulo de quebra de referências.

## Consequências

- O número `0030` não deve ser reutilizado por decisões futuras; novos ADRs seguem a partir do próximo número livre (`0044`).

## Como verificar

Conferir a existência deste arquivo e a entrada `0030` marcada como `Aposentado` em [docs/adr/README.md](README.md).
