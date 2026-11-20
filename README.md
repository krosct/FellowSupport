# FellowSupport

Assistente de suporte ao cliente com respostas técnicas personalizadas por perfil (nível técnico, estilo de
comunicação e canal), feito para o desafio técnico "Estágio em IA e Engenharia de Prompt".

> README mínimo da Etapa 0 (fundação). O README completo, com arquitetura, exemplos de saída e limitações, chega
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
e `OPENROUTER_API_KEY` preenchida; nesta etapa nenhuma geração é feita.

## Rodar a API (e o site)

```bash
cd frontend && npm install && npm run build && cd ..   # gera frontend/dist
.venv/bin/uvicorn app.adapters.api.main:app --port 8000
```

Abra http://127.0.0.1:8000/. A API serve o build do front em `/`. Rotas: `GET /healthz`, `GET /api/meta`,
`GET /api/profiles` e `GET /api/tickets` (documentação interativa em `/api/docs`).

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
```

Todos aceitam `--json`. Códigos de saída: 0 sucesso, 1 uso ou validação, 2 não encontrado, 3 provedor de LLM.

## Testes e lint

```bash
.venv/bin/pytest -q
.venv/bin/ruff check .
```
