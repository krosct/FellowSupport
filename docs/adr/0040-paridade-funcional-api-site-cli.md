# ADR 0040 · Paridade funcional entre site, API e CLI

- **Status**: Aceito (complementado pelo [ADR 0041](0041-cli-adaptador-direto-do-nucleo.md) na escolha de transporte da CLI)
- **Data**: 2026-11-23

## Contexto

O sistema oferece duas interfaces sobre o mesmo núcleo de domínio e serviços: a API HTTP (consumida pelo site React) e a CLI. Se cada interface aceitasse entradas ou fluxos próprios (como ticket digitado fora do catálogo, geração implícita dentro da comparação ou critérios de paginação distintos), as regras divergiriam entre site, API e CLI.

## Opções consideradas

### 1. Contrato funcional único entre site, API e CLI (escolhida)

- **Prós**: As mesmas capacidades e validações valem em todas as interfaces (`meta`, CRUD de perfis e tickets, criação/listagem/remoção de versões de prompt sem edição in-place, geração com cache e confirmação de substituição, histórico paginado e comparação de execuções já geradas); reduz código especial por interface.
- **Contras**: Exige cadastrar o ticket no catálogo antes de gerar e gerar as execuções antes de comparar.
- **Custo**: Baixo: os casos de uso compartilhados vivem em `app/services/`, consumidos simetricamente por API e CLI.
- **Risco**: Baixo: testes de contrato garantem que `--json` da CLI e respostas HTTP da API exponham os mesmos metadados e regras.

### 2. Fluxos exclusivos por interface

- **Prós**: Atalhos convenientes na CLI (como ticket inline ou comparação que dispara gerações).
- **Contras**: Regras divergentes entre CLI, API e site; documentação e testes duplicados; comparação passa a esconder custo e cache de geração.
- **Custo**: Médio a alto na manutenção.
- **Risco**: Alto: inconsistência de comportamento e de validação entre interfaces.

## Decisão

Site, API e CLI oferecem exatamente as mesmas funcionalidades e regras de negócio:

- **Ticket sempre do catálogo**: `generate` recebe perfil e ticket cadastrados (`profile_id` / `--customer`, `ticket_id` / `--ticket`).
- **Gerar e comparar são ações distintas**: `compare` recebe apenas execuções já geradas (uma por versão, sem acertos de cache, no mesmo cenário, validadas por `check_comparable`). Se já houver comparação das mesmas execuções, oferece carregar a salva (ADR 0038) ou fazer outra do zero; salvar exige as notas e justificativas de todas as execuções comparadas.
- **Paridade de recursos**: `meta`, CRUD de clientes e tickets (`list|create|update|delete`), gestão de versões imutáveis de prompt (`list|create|delete`, sem edição in-place), filtros de histórico (incluindo `cache_key`) e paginação (`10`, `20`, `50` ou `100` itens por página).
- **Modo `all` com falha parcial**: só falha por completo se todos os tipos falharem; se apenas parte falhar, devolve os resultados válidos e exibe a mesma mensagem de aviso (`warning`, em toast no site e em `stderr` na CLI).

## Por que vence

- **O que ganha e o que perde**: Ganha previsibilidade, menor superfície de erro e uma única regra de negócio para testar e documentar. Perde atalhos isolados exclusivos de uma interface.
- **Por que compensa**: Compensa porque a paridade elimina fluxos paralelos no núcleo e garante que qualquer cenário reproduzido no site possa ser repetido com exatidão na CLI ou na API.

## Consequências

- Qualquer nova operação de domínio exposta no site deve estar disponível com as mesmas regras na API e na CLI (atrás dos serviços comuns, ADR 0041).
- Testes garantem a paridade de metadados (`meta --json` vs. `GET /api/meta`), paginação, modo `all` e comparação.

## Como verificar

`.venv/bin/pytest -q tests/test_cli.py tests/test_cli_comparison.py tests/test_api_comparison.py tests/test_api_generate.py`
