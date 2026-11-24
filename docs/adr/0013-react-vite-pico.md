# ADR 0013 · React + Vite (JavaScript) + Pico CSS

- **Status**: Aceito
- **Data**: 2026-11-20

## Contexto

O projeto inclui uma interface web simples para operar o assistente e comparar execuções, mantendo o esforço principal concentrado no núcleo e nos prompts.

## Opções consideradas

### React + Vite em JavaScript, `@picocss/pico` e `app.css` com tokens; abas com estado e hash, sem react-router

- **Prós**: Estilo semântico pronto com modo escuro; poucas classes; build rápido; componentes reutilizáveis.
- **Contras**: Aparência genérica; JavaScript sem checagem de tipos.
- **Custo**: Baixo.
- **Risco**: Baixo: o visual genérico é aceitável para o escopo.

### Tailwind CSS

- **Prós**: Controle fino do visual.
- **Contras**: Configuração extra e classes verbosas nos componentes.
- **Custo**: Médio.
- **Risco**: Baixo.

### Biblioteca de componentes pesada (por exemplo MUI)

- **Prós**: Componentes prontos e ricos.
- **Contras**: Bundle grande; curva de tema; muito além do necessário.
- **Custo**: Médio.
- **Risco**: Médio: peso e complexidade.

### CSS escrito do zero

- **Prós**: Nenhuma dependência de estilo.
- **Contras**: Exige mais tempo e manutenção de estilo em um projeto cujo foco principal é o motor de geração e avaliação de prompts.
- **Custo**: Alto.
- **Risco**: Médio: inconsistência visual.

## Decisão

React + Vite em JavaScript, Pico CSS para a base semântica e `src/styles/app.css` para tokens e ajustes.

## Por que vence

- **O que ganha e o que perde**: Ganha rapidez e boa aparência por padrão. Perde personalização visual profunda.
- **Por que compensa**: Compensa porque entrega uma interface limpa e acessível com mínimo esforço de manutenção, sem desviar o projeto do núcleo de prompts.

## Consequências

Componentes reutilizáveis ficam em `src/components/`; `src/api/client.js` é o único ponto de `fetch`; diálogos nativos do navegador são proibidos (toast próprio).

## Como verificar

`npm run build` passa; verificação visual no navegador (normal, hover, foco e mobile); busca por `alert(`, `confirm(` e `prompt(` no código do front retorna vazio.
