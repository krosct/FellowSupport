# ADR 0013 · React + Vite (JavaScript) + Pico CSS

- **Status**: Aceito
- **Data**: 2026-11-20

## Contexto

A interface web é opcional no PDF, mas conta como diferencial. Precisa ficar bonita e simples sem desviar o esforço da engenharia de prompt.

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
- **Contras**: Mais tempo em um front que não é o foco da avaliação.
- **Custo**: Alto.
- **Risco**: Médio: inconsistência visual.

## Decisão

React + Vite em JavaScript, Pico CSS para a base semântica e `src/styles/app.css` para tokens e ajustes.

## Por que vence

- **O que ganha e o que perde**: Ganha rapidez e boa aparência por padrão. Perde personalização visual profunda.
- **Por que compensa**: Compensa porque o foco do desafio é o prompt, e uma interface limpa já cumpre o papel de diferencial.

## Consequências

Componentes reutilizáveis ficam em `src/components/`; `src/api/client.js` é o único ponto de `fetch`; diálogos nativos do navegador são proibidos (toast próprio).

## Como verificar

`npm run build` passa; verificação visual no navegador (normal, hover, foco e mobile); busca por `alert(`, `confirm(` e `prompt(` no código do front retorna vazio.
