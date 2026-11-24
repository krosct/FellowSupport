# ADR 0004 · Saída estruturada com schema Pydantic e reparo

- **Status**: Aceito
- **Data**: 2026-11-20

## Contexto

O projeto exige um diagnóstico estruturado e verificável (hipóteses, evidências, faltantes e conclusão) e saídas estruturadas nos outros três conteúdos. Modelos gratuitos variam no suporte nativo a saída estruturada.

## Opções consideradas

### Schema Pydantic por tipo, `LLM_STRUCTURED_MODE=json_schema|json_object|prompt`, validação e 1 retentativa de reparo

- **Prós**: Saída verificável por código; fallback configurável conforme a capacidade do modelo; o erro de validação volta ao modelo para correção.
- **Contras**: Mais código de adaptação; a retentativa pode dobrar a latência e o consumo em casos ruins.
- **Custo**: Médio: schemas, modos e testes.
- **Risco**: Baixo: modelo que ignore o schema falha de forma controlada (`InvalidLLMOutput`).

### Texto livre

- **Prós**: Simples; qualquer modelo responde.
- **Contras**: Impossível validar; a interface depende de parsing frágil; contraria o pedido de saída verificável.
- **Custo**: Baixo.
- **Risco**: Alto: renderização quebra com mudanças pequenas de formato.

### Tool calling (chamada de função)

- **Prós**: Estrutura garantida por parte dos provedores que suportam.
- **Contras**: Poucos modelos gratuitos suportam bem; acopla o fluxo a um recurso opcional.
- **Custo**: Médio.
- **Risco**: Alto: indisponibilidade em modelos gratuitos.

### Somente JSON schema estrito

- **Prós**: Melhor garantia quando o modelo suporta.
- **Contras**: Sem fallback, falha em modelos sem esse suporte.
- **Custo**: Baixo.
- **Risco**: Médio: troca de modelo pode quebrar a geração.

## Decisão

Um schema Pydantic por tipo de conteúdo, modo de saída configurável com padrão `json_schema`, validação sempre aplicada e uma única retentativa de reparo com o erro de validação.

## Por que vence

- **O que ganha e o que perde**: Ganha verificabilidade e resiliência a modelos diferentes. Perde simplicidade e, no pior caso, uma chamada extra.
- **Por que compensa**: Compensa porque a verificabilidade por schema é um requisito do projeto e o fallback configurável evita depender de um único modelo.

## Consequências

Todas as saídas passam por `model_validate`. Falha após o reparo vira `InvalidLLMOutput` (ADR 0018) e é gravada como execução com erro.

## Como verificar

Testes com saída válida, inválida e reparável usando o LLM falso; teste de cada modo no adaptador; schema do diagnóstico com hipóteses, evidências, faltantes e conclusão.
