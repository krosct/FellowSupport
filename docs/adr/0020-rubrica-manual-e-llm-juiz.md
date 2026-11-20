# ADR 0020 · Rubrica em constante única, avaliação manual e LLM-juiz separados

- **Status**: Aceito
- **Data**: 2026-11-20

## Contexto

O PDF exige uma rubrica fixa de três critérios com notas de 1 a 5 e justificativa escrita pelo autor, e trata a autoavaliação como evidência. Um LLM-juiz pode apoiar, mas não substitui.

## Opções consideradas

### Constante `RUBRIC` em `domain/rubric.py`; avaliação manual em `evaluation` e sugestão do juiz em `llm_evaluation`, em campos separados

- **Prós**: Cumpre o PDF e acrescenta um diferencial; a rubrica é consumida por validação, API e front.
- **Contras**: O juiz tem viés (especialmente se for o mesmo modelo que gerou) e gasta chamadas extras.
- **Custo**: Baixo a médio: um prompt e uma chamada por avaliação sugerida.
- **Risco**: Médio: viés documentado; a sugestão nunca vira nota final sozinha.

### Somente LLM-juiz

- **Prós**: Automático e barato.
- **Contras**: Contraria o PDF, que pede justificativa escrita pelo autor.
- **Custo**: Baixo.
- **Risco**: Alto: descumprimento do requisito.

### Somente avaliação manual

- **Prós**: Cumpre o PDF com o menor esforço.
- **Contras**: Perde um diferencial e um segundo ponto de vista.
- **Custo**: Baixo.
- **Risco**: Baixo.

## Decisão

Rubrica em constante única; avaliação manual obrigatória e sugestão opcional do juiz (`prompts/judge/v1`, modelo `LLM_JUDGE_MODEL`), guardadas separadas.

## Por que vence

- **O que ganha e o que perde**: Ganha conformidade e um segundo olhar. Perde alguma simplicidade.
- **Por que compensa**: Compensa porque a separação evita que a sugestão automática seja confundida com a avaliação do autor.

## Consequências

Critérios, rótulos e escala existem só em `rubric.py`; `GET /api/meta` os publica.

## Como verificar

Teste da constante (3 critérios, escala 1 a 5 com rótulos) e de validação de notas fora do intervalo; resposta de `/api/meta` com a rubrica.
