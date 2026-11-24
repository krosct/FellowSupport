# ADR 0025 · Idioma pt-BR e horários com fuso configurado

- **Status**: Aceito
- **Data**: 2026-11-20

## Contexto

O público do produto fictício fala português e os clientes de exemplo incluem leigos. É preciso definir idioma de prompts, saídas, documentação e código, e como gravar horários.

## Opções consideradas

### Prompts, saídas, documentação e comentários em pt-BR; identificadores e chaves JSON em inglês; horários em ISO 8601 com o fuso de `APP_TIMEZONE` (`America/Sao_Paulo`)

- **Prós**: Vocabulário e exemplos coerentes com a saída esperada; menor risco de respostas em inglês para clientes leigos; chaves JSON em inglês mantêm uniformidade com identificadores do código.
- **Contras**: Alguns modelos seguem melhor instruções em inglês; exige cuidado com acentuação nos arquivos.
- **Custo**: Baixo.
- **Risco**: Baixo: a diferença de desempenho é medida pela rubrica.

### Prompt em inglês com saída em pt-BR

- **Prós**: Possível ganho de aderência às instruções em alguns modelos.
- **Contras**: Misturar idiomas aumenta o risco de respostas em inglês ou com termos não traduzidos.
- **Custo**: Baixo.
- **Risco**: Médio.

### Tudo em inglês

- **Prós**: Padrão de mercado para código e documentação.
- **Contras**: Distancia o prompt do idioma do cliente e do avaliador.
- **Custo**: Baixo.
- **Risco**: Médio.

## Decisão

Conteúdo textual em pt-BR; identificadores e chaves JSON em inglês; timestamps ISO 8601 com `zoneinfo` e `APP_TIMEZONE`.

## Por que vence

- **O que ganha e o que perde**: Ganha coerência entre prompt, saída e leitor. Perde a possível vantagem de instruções em inglês em alguns modelos.
- **Por que compensa**: Compensa porque a adaptação ao cliente é o foco, e o idioma do cliente é pt-BR.

## Consequências

Enums do catálogo usam os valores em português com acentuação definidos pelo projeto (`leigo`, `intermediário`, `avançado`, `e-mail`).

## Como verificar

Teste: timestamps gravados têm deslocamento do fuso configurado; catálogo carrega valores acentuados sem erro.
