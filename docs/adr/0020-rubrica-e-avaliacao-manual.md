# ADR 0020 · Rubrica em constante única e avaliação manual

- **Status**: Aceito
- **Data**: 2026-11-20

## Contexto

O projeto define uma rubrica fixa de três critérios (clareza, adequação ao cliente e acionabilidade) com notas de 1 a 5 e justificativa escrita pelo avaliador humano.

## Opções consideradas

### Constante `RUBRIC` em `domain/rubric.py` e avaliação manual em `evaluation`

- **Prós**: Atende ao requisito de avaliação humana; critérios, rótulos, escala e limites ficam em um único local (SSOT) consumido por validação, API, CLI e front-end.
- **Contras**: Exige que o avaliador preencha todas as notas e justificativas manualmente.
- **Custo**: Baixo: um módulo de domínio, validação Pydantic e formulário compartilhado.
- **Risco**: Baixo: avaliação direta pelo autor sem dependência externa.

### Rubrica repetida por adaptador (front, CLI e API)

- **Prós**: Cada camada evolui independente no curto prazo.
- **Contras**: Risco alto de divergência entre critérios, rótulos e limites nas diferentes interfaces.
- **Custo**: Médio.
- **Risco**: Médio: notas inválidas ou rótulos inconsistentes entre CLI e site.

## Decisão

Rubrica em constante única (`domain/rubric.py`) e avaliação manual obrigatória gravada em `evaluation`.

## Por que vence

- **O que ganha e o que perde**: Ganha consistência entre todas as interfaces e simplicidade no fluxo de avaliação. Perde a separação caso cada cliente quisesse critérios diferentes.
- **Por que compensa**: A rubrica é fixa no domínio e publicar via `/api/meta` evita duplicação no front-end e na CLI.

## Consequências

Critérios, rótulos e escala existem só em `rubric.py`; `GET /api/meta` os publica.

## Como verificar

Teste da constante (3 critérios, escala 1 a 5 com rótulos) e de validação de notas fora do intervalo; resposta de `/api/meta` com a rubrica.
