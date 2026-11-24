# 🤖 FellowSupport

Assistente de suporte técnico ao cliente (produto fictício **NuvemPonto**) que gera respostas personalizadas por **perfil de cliente** e compara versões de prompt com uma rubrica fixa. Desenvolvido para o desafio **Estágio em IA e Engenharia de Prompt**.

## ✨ O que o sistema faz

Recebe um **perfil** ([`catalog/profiles.json`](catalog/profiles.json): nível técnico, estilo de comunicação e canal) e um **ticket** ([`catalog/tickets.json`](catalog/tickets.json)) para gerar 4 conteúdos com prompts versionados (`v1`–`v4`):

1. 🔍 **Diagnóstico** (`diagnosis`) — hipóteses ordenadas, evidências, dados faltantes e conclusão.
2. 🛠️ **Passo a passo** (`resolution_steps`) — instruções adaptadas ao perfil e ao canal.
3. ❓ **Perguntas de esclarecimento** (`clarifying_questions`) — priorizadas para destravar o atendimento.
4. 🗺️ **Resumo visual do fluxo** (`flow_summary`) — árvore de decisão em JSON renderizada em fluxograma ASCII determinístico.

Cada execução é salva em JSON com timestamp e hash do prompt, usa **cache SHA-256** para evitar chamadas equivalentes repetidas e permite **comparar versões** no mesmo cenário pela rubrica fixa (**Clareza**, **Adequação ao nível do cliente** e **Acionabilidade**, notas 1–5 + justificativa).

## 📋 Pré-requisitos

- **Python 3.12** e [**uv**](https://docs.astral.sh/uv/) (ou `python3.12 -m venv`)
- **Node.js 20.19+** e `npm` *(opcional — necessário apenas para gerar a interface web)*
- **Chave OpenRouter** *(opcional — por padrão roda offline com `LLM_PROVIDER=fake`, sem custo)*

## 🚀 Instalação e uso rápido

```bash
git clone https://github.com/krosct/FellowSupport.git && cd FellowSupport
cp .env.example .env                 # padrão LLM_PROVIDER=fake (sem chave, sem custo)
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -r requirements-dev.txt
```

### 💻 CLI (adaptador direto do núcleo, sem precisar subir servidor)

```bash
# 1. Gerar um conteúdo (--type all gera os 4 em paralelo)
.venv/bin/python -m app.adapters.cli.main generate --customer marta --ticket t-2fa --type flow_summary

# 2. Repetir o comando: acerta o cache (0 chamadas ao LLM, cache_hit: true)
.venv/bin/python -m app.adapters.cli.main generate --customer marta --ticket t-2fa --type flow_summary

# 3. Gerar versões diferentes no mesmo cenário e comparar pela rubrica
.venv/bin/python -m app.adapters.cli.main generate --customer marta --ticket t-2fa --type diagnosis --version v1
.venv/bin/python -m app.adapters.cli.main generate --customer marta --ticket t-2fa --type diagnosis --version v4
.venv/bin/python -m app.adapters.cli.main compare <id_v1> <id_v4>
```

Outros comandos: `meta`, `profile|ticket list|create|update|delete`, `prompt list|create|delete`, `history generation|comparison`, `show <id>` (detalhes com `--help`). Use `--no-cache` para ignorar a leitura do cache e `--json` para saída estruturada.

### 🌐 Interface Web e API (FastAPI + React)

```bash
(cd frontend && npm install && npm run build)   # gera frontend/dist
.venv/bin/uvicorn app.adapters.api.main:app --port 9713
```

Acesse **http://127.0.0.1:9713** (abas *Cliente*, *Ticket*, *Prompt*, *Gerar*, *Comparar* e *Histórico*) ou **http://127.0.0.1:9713/api/docs** (Swagger). Principais rotas: `GET /api/meta`, `CRUD /api/profiles|tickets|prompts`, `POST /api/generate`, `GET /api/runs`, `POST/GET /api/comparisons` e `GET /healthz`.

### 🔑 Ativar modelo real (OpenRouter)

Edite o `.env` (nunca versionado; veja todas as variáveis em [`.env.example`](.env.example)):

```ini
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-...   # https://openrouter.ai/keys (apenas modelos :free)
LLM_MAX_TOKENS=12000           # folga para modelos que raciocinam antes do JSON
```

> 💡 Para rodar um comando sem gastar cota mesmo com `.env` em `openrouter`, prefixe com `LLM_PROVIDER=fake`.

## 📄 Persistência e exemplo de JSON

Os arquivos gerados localmente ficam fora do Git:

- `var/runs/AAAA-MM-DD/<ts>_<run_id>.json` — execução completa (`prompt_messages`, `output`, `llm_calls`, `cache_key`, `cache_hit`, `evaluation`)
- `var/cache/<sha256>.json` — ponteiro da chave de cache para a execução de origem
- `var/comparisons/<id>.json` — comparação salva com notas, justificativas e vencedor
- `fellowsupport.log` — eventos em JSON Lines (`generation`, `generation_batch`, `evaluation`, `comparison`)

Exemplo real resumido (veja todos os exemplos em [`samples/`](samples/README.md)):

```json
{
  "run_id": "aba69b5c89e1", "status": "ok", "customer_id": "bianca",
  "ticket": { "id": "t-webhook", "title": "API e webhook retornando 401 e 429" },
  "content_type": "clarifying_questions", "prompt_version": "v4",
  "provider": "openrouter", "model": "deepseek/deepseek-v4.1-flash-1017",
  "cache_hit": false,
  "output": { "questions": [{ "priority": 1, "question": "..." }], "can_proceed_without_answers": false },
  "evaluation": {
    "clarity": { "score": 5, "justification": "..." },
    "customer_fit": { "score": 5, "justification": "..." },
    "actionability": { "score": 4, "justification": "..." }
  }
}
```

## 🏗️ Arquitetura resumida

Arquitetura **Hexagonal (Ports and Adapters)** verificada por teste (`tests/test_architecture.py`):

```text
frontend/ (React + Vite + Pico) ──▶ adapters/api (FastAPI) ──┐
CLI (argparse) ───────────────────▶ adapters/cli            ├──▶ services/ ──▶ domain/ ◀── ports/
                                                             └──▶ adapters/{llm,storage}/
```

- `app/config.py` e `app/container.py` — configuração única (`Settings`) e injeção das dependências
- `app/domain/` — schemas Pydantic, rubrica, motor de prompts (`string.Template`), chave de cache e fluxograma ASCII (sem I/O)
- `app/services/` — geradores (com 1 reparo automático em JSON inválido), histórico, avaliação, catálogo e comparação justa
- `catalog/` — 5 perfis (`marta`, `rafael`, `bianca`, `jorge`, `amanda`) e 2 tickets (`t-2fa`, `t-webhook`)
- `prompts/v1..v4/` — versões imutáveis validadas por `content_sha256` em `meta.json` (a mais nova é a padrão)

## 🧠 Engenharia de prompt e limitações

- **Estratégias**: persona e limites (`system.md`), contexto delimitado contra injeção (`<ticket>...</ticket>`), adaptação por perfil (`adaptation.json`), decomposição do diagnóstico, saída estruturada com schema estrito + 1 reparo (`repair.md`) e fluxograma por código.
- **Notas do experimento e limitações**: evolução `v1`→`v4`, avaliações na rubrica, trade-offs e limitações (1 execução por célula, cortes por orçamento de raciocínio, cache sem TTL) em [`PROMPT_ENGINEERING_NOTES.md`](PROMPT_ENGINEERING_NOTES.md) e decisões em [`docs/adr/`](docs/adr/README.md).

## 🧪 Testes, qualidade e deploy

```bash
.venv/bin/pytest -q            # 694 testes offline (provedor fake, sem rede)
.venv/bin/ruff check .         # lint e formatação
(cd frontend && npm run build) # build da interface web
```

- **CI/CD**: [`.github/workflows/ci-cd.yml`](.github/workflows/ci-cd.yml) executa `ruff`, `pytest`, build do front-end, auditoria de dependências, smoke test e deploy na VPS via `krosct/devkit`.
- **Deploy**: configurado via [`deploy.conf`](deploy.conf) (systemd + Caddy, `RATE_LIMIT_PER_MIN` por IP e proteção administrativa via `ADMIN_API_KEY`; detalhes nos ADRs [0024](docs/adr/0024-deploy.md), [0033](docs/adr/0033-limite-de-taxa-por-ip.md) e [0034](docs/adr/0034-contrato-do-deploy-conf.md)).
