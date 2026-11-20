# ADR 0005 · Prompts como arquivos versionados com string.Template

- **Status**: Aceito
- **Data**: 2026-11-20

## Contexto

Os prompts são o principal objeto de avaliação. Precisam ser lidos, comparados por diff e versionados de forma explícita, sem se misturar ao código.

## Opções consideradas

### Arquivos Markdown em `prompts/<versão>/` renderizados com `string.Template` e `meta.json` por versão

- **Prós**: Diff legível entre versões (`git diff prompts/v1 prompts/v2`); sem dependência extra; `meta.json` registra mudanças, motivo e efeito esperado.
- **Contras**: Placeholder faltando só aparece na renderização; sintaxe `$var` limitada, sem laços.
- **Custo**: Baixo.
- **Risco**: Baixo: coberto por teste que renderiza todos os arquivos com todos os perfis.

### Strings em arquivos `.py`

- **Prós**: Sem leitura de arquivos; verificação estática possível.
- **Contras**: Mistura prompt e código; diff ruim; edição exige conhecer Python.
- **Custo**: Baixo.
- **Risco**: Médio: prompts crescem de forma desorganizada.

### Jinja2 ou YAML

- **Prós**: Lógica condicional e laços nos templates.
- **Contras**: Dependência extra; incentiva lógica complexa dentro do prompt, o oposto de prompts claros e curtos.
- **Custo**: Médio.
- **Risco**: Médio: injeção de template e aumento de complexidade.

## Decisão

Prompts em Markdown dentro de `prompts/<versão>/`, com `adaptation.json` para as regras por perfil e `meta.json` para o versionamento.

## Por que vence

- **O que ganha e o que perde**: Ganha legibilidade, diff e zero dependência. Perde recursos de template avançados, de que o projeto não precisa.
- **Por que compensa**: Compensa porque o avaliador lê o prompt como documento e o diff entre versões demonstra a mudança.

## Consequências

A lógica de adaptação fica em dados (`adaptation.json`) e no `PromptBuilder`, não dentro dos templates.

## Como verificar

Teste que renderiza todos os arquivos de cada versão com todos os perfis e tickets do catálogo sem erro de placeholder.
