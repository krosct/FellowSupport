# FellowSupport

Assistente de suporte ao cliente com respostas técnicas personalizadas por perfil (nível técnico, estilo de
comunicação e canal), feito para o desafio técnico "Estágio em IA e Engenharia de Prompt".

> README mínimo (até a Etapa 2: os quatro tipos de conteúdo). O README completo, com arquitetura, exemplos de saída e limitações, chega
> na Etapa 6. O plano está em [`docs/planejamento/`](docs/planejamento/) e as decisões em [`docs/adr/`](docs/adr/).

Repositório: https://github.com/krosct/FellowSupport.git

## Requisitos

- Python 3.12 (o `uv` instala sozinho) e [`uv`](https://docs.astral.sh/uv/)
- Node 20 ou superior e npm (somente para o front-end)

## Instalação

```bash
uv venv .venv --python 3.12
uv pip install -r requirements-dev.txt
cp .env.example .env        # o padrão LLM_PROVIDER=fake roda sem chave
```

Sem `uv`: `python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt`.

O `.env` guarda segredos e nunca é versionado. Chamadas reais ao LLM só acontecem com `LLM_PROVIDER=openrouter`
e `OPENROUTER_API_KEY` preenchida; com `LLM_PROVIDER=fake` (padrão) as respostas são simuladas e determinísticas.
Os modelos gratuitos "pensam" antes de responder: mantenha `LLM_MAX_TOKENS` em 8000 ou mais (ADR 0026). O modelo padrão tem raciocínio obrigatório e recusa `LLM_REASONING=off`; ver ADR 0027.

## Rodar a API (e o site)

```bash
cd frontend && npm install && npm run build && cd ..   # gera frontend/dist
.venv/bin/uvicorn app.adapters.api.main:app --port 8000
```

Abra http://127.0.0.1:8000/. A API serve o build do front em `/`. Escolha o perfil, o ticket e o conteúdo (diagnóstico, passo a passo,
perguntas de esclarecimento, resumo visual do fluxo ou **Todos**) e clique em **Gerar**: o site mostra o conteúdo e o caminho
do JSON salvo. Em "Todos" os quatro são gerados em paralelo, em abas, cada um com o seu JSON; a falha de um não afeta os outros. Rotas: `GET /healthz`, `GET /api/meta`, `GET /api/profiles`,
`GET /api/tickets`, `GET /api/prompt-versions` e `POST /api/generate` (`content_type` com os quatro tipos ou `all`; `use_cache`, padrão `true`;
documentação interativa em `/api/docs`).

## Rodar o front em modo de desenvolvimento

```bash
.venv/bin/uvicorn app.adapters.api.main:app --port 8000   # em um terminal
cd frontend && npm run dev                                 # em outro: http://localhost:5173
```

O Vite encaminha `/api` e `/healthz` para a porta 8000.

## CLI

```bash
.venv/bin/python -m app.adapters.cli.main profiles            # perfis de cliente
.venv/bin/python -m app.adapters.cli.main tickets             # tickets de exemplo
.venv/bin/python -m app.adapters.cli.main tickets --id t-2fa  # ticket completo
.venv/bin/python -m app.adapters.cli.main versions            # versões de prompt (com hash)
.venv/bin/python -m app.adapters.cli.main generate --customer marta --ticket t-2fa      # diagnóstico (padrão)
.venv/bin/python -m app.adapters.cli.main generate --customer marta --ticket t-2fa --type resolution_steps
.venv/bin/python -m app.adapters.cli.main generate --customer marta --ticket t-2fa --type clarifying_questions
.venv/bin/python -m app.adapters.cli.main generate --customer marta --ticket t-2fa --type flow_summary  # fluxograma ASCII
.venv/bin/python -m app.adapters.cli.main generate --customer marta --ticket t-2fa --type all          # os quatro, em paralelo
.venv/bin/python -m app.adapters.cli.main generate --customer bianca --text "A API devolve 500."
.venv/bin/python -m app.adapters.cli.main generate --customer marta --ticket t-2fa --no-cache      # ignora o cache
```

Todos aceitam `--json`. `--type` aceita `diagnosis`, `resolution_steps`, `clarifying_questions`, `flow_summary` e `all`. `generate`
imprime o conteúdo em texto legível (o fluxograma em ASCII, desenhado por código a partir da árvore de decisão) e
`JSON salvo em: var/runs/AAAA-MM-DD/<carimbo>_<id>.json`; com `all`, um bloco e um JSON por tipo, e a falha de um tipo não
impede a saída dos outros. Códigos de saída: 0 sucesso, 1 uso ou validação, 2 não encontrado, 3 provedor de LLM.

### Cache

Gerar duas vezes a mesma entrada (mesmo perfil, ticket, tipo, versão e hash do prompt, provedor, modelo e parâmetros) não
chama o LLM na segunda vez: a CLI mostra `cache hit (origem <id>, sem chamar o LLM)` e o JSON salvo traz `cache_hit: true`,
`source_run_id` e latência de ~0 ms. O cache vive em `var/cache/<sha256>.json` e aponta para a execução de origem; execuções
com erro nunca entram nele. Para gerar de novo: `--no-cache` na CLI, `"use_cache": false` na API ou desmarcar **Usar cache**
no site; `CACHE_ENABLED=false` no `.env` desliga o cache de vez. Detalhes no ADR 0028.

Exemplo do fluxograma (provedor `fake`):

```text
(INÍCIO) Cliente relata o problema
│
▼
<1> Os dados do cadastro estão corretos?
├─ Sim ─▶ <2> A ação funciona ao repetir?
│         ├─ Sim ─▶ [3] FIM: Problema resolvido
│         └─ Não ─▶ [4] Coletar a mensagem de erro e o horário
│                   │
│                   ▼
│                   [5] FIM: Escalar para o nível 3 com os detalhes
└─ Não ─▶ [6] Corrigir os dados do cadastro
          │
          ▼
          (segue em <2>)
```

Atenção: o `.env` com `LLM_PROVIDER=openrouter` gasta cota real a cada comando `generate`. Para ensaiar sem custo, use
`LLM_PROVIDER=fake .venv/bin/python -m app.adapters.cli.main generate ...`.

## Teste real com o provedor (manual)

```bash
.venv/bin/python scripts/smoke_llm.py --max-tokens 6000   # uma chamada real; anota em var/smoke/calls.log
```

Exige `LLM_PROVIDER=openrouter` e a chave no `.env`; sem elas o script informa que o teste real está bloqueado.

## Testes e lint

```bash
.venv/bin/pytest -q
.venv/bin/ruff check .
```
