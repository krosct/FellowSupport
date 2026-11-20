# ADR 0022 · Defesa contra injeção de prompt pelo ticket

- **Status**: Aceito
- **Data**: 2026-11-20

## Contexto

O texto do ticket é entrada não confiável e pode conter instruções que tentem alterar o comportamento do assistente.

## Opções consideradas

### Ticket delimitado por `<ticket>...</ticket>`, instrução explícita de tratá-lo como dado e limite `MAX_TICKET_CHARS`

- **Prós**: Reduz o sequestro das instruções; o limite controla custo e superfície de ataque; simples e transparente.
- **Contras**: Não elimina o risco; modelos podem ainda obedecer a instruções do ticket.
- **Custo**: Baixo.
- **Risco**: Médio: defesa parcial, declarada como limitação.

### Sem delimitação

- **Prós**: Prompt mais simples.
- **Contras**: O ticket se confunde com as instruções do sistema.
- **Custo**: Baixo.
- **Risco**: Alto.

### Filtro de palavras suspeitas

- **Prós**: Bloqueia ataques conhecidos.
- **Contras**: Falsos positivos e fácil de contornar; tickets legítimos podem conter essas palavras.
- **Custo**: Médio.
- **Risco**: Médio.

## Decisão

Delimitar o ticket com tags, instruir o modelo a tratá-lo como dado e limitar o tamanho por `MAX_TICKET_CHARS`.

## Por que vence

- **O que ganha e o que perde**: Ganha uma barreira barata e explicável. Perde a garantia absoluta, que nenhuma técnica de prompt oferece.
- **Por que compensa**: Compensa porque é a mitigação padrão de menor custo e fica documentada com sua limitação.

## Consequências

A instrução de tratar o ticket como dado vive no `system.md` de cada versão.

## Como verificar

Teste com ticket malicioso no LLM falso verificando que as mensagens enviadas contêm as tags e a instrução; teste de ticket acima do limite recusado com `ValidationFailed`.
