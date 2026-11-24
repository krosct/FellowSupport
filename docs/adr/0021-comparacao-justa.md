# ADR 0021 · Comparação justa garantida por código

- **Status**: Aceito
- **Data**: 2026-11-20

## Contexto

Para comparar versões de prompt de forma válida, é necessário manter cliente, ticket, provedor/modelo e configurações equivalentes. Confiar apenas na disciplina de quem executa é frágil.

## Opções consideradas

### O serviço de comparação recusa execuções com perfil, ticket, tipo, modelo efetivo ou parâmetros diferentes

- **Prós**: A justiça deixa de depender de disciplina; qualquer comparação salva é válida por construção.
- **Contras**: Mais regras e testes; exige registrar o modelo efetivamente usado.
- **Custo**: Baixo.
- **Risco**: Baixo.

### Confiar no usuário

- **Prós**: Sem código.
- **Contras**: Comparações injustas passam despercebidas e invalidam a conclusão.
- **Custo**: Baixo.
- **Risco**: Alto.

### Apenas avisar na interface

- **Prós**: Fácil de implementar.
- **Contras**: Avisos são ignorados e a CLI não os mostra de forma confiável.
- **Custo**: Baixo.
- **Risco**: Médio.

## Decisão

Validar no serviço `comparison.py` a igualdade de perfil, ticket, tipo, modelo efetivo (`model_used`) e parâmetros; só a versão do prompt pode diferir.

## Por que vence

- **O que ganha e o que perde**: Ganha validade científica da comparação. Perde flexibilidade de comparar cenários diferentes, que não é objetivo.
- **Por que compensa**: Compensa porque a conclusão sobre qual prompt é melhor só vale em condições equivalentes.

## Consequências

Erros viram `ValidationFailed` com a lista de campos divergentes.

## Como verificar

Testes: cada campo divergente (perfil, ticket, tipo, modelo, temperatura, `max_tokens`, modo) causa recusa; cenário equivalente é aceito.
