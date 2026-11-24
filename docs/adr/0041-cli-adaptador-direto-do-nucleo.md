# ADR 0041 · CLI como adaptador de entrada direto do núcleo

- **Status**: Aceito (complementa os ADRs [0002](0002-arquitetura-hexagonal.md) e [0040](0040-paridade-funcional-api-site-cli.md))
- **Data**: 2026-11-23

## Contexto

Pela arquitetura hexagonal adotada no ADR 0002, API HTTP e CLI são adaptadores primários (*driving adapters*) no mesmo nível: ambos consomem os casos de uso do núcleo (`app/services/` e `Container`) com a mesma paridade funcional (ADR 0040), enquanto o limite de taxa por IP (`RATE_LIMIT_PER_MIN`, ADR 0033) protege especificamente a borda HTTP exposta na rede.

## Opções consideradas

### 1. CLI chamando diretamente `Container` e `app/services/` (escolhida)

- **Prós**: CLI 100% independente da API e do FastAPI (funciona sem servidor no ar); reduz latência e código de transporte (`urllib`, DTOs duplicados); reforça a arquitetura hexagonal com dois adaptadores primários simétricos sobre os mesmos serviços (`services/meta.py`, `catalog.py`, `generators.py`, `history.py`, `comparison.py`).
- **Contras**: A CLI não passa pelo `RATE_LIMIT_PER_MIN` da API HTTP; quem usa a CLI localmente usa diretamente sua própria chave/provedor do `.env`.
- **Custo**: Baixo: compartilhar `services/meta.py` e os resumos (`summarize_run`, `summarize_comparison`, `BatchSummary`) para evitar duplicação com `adapters/api/routers.py`.
- **Risco**: Baixo: um teste em `tests/test_architecture.py` garante que `adapters/cli` nunca importe `fastapi` nem `app.adapters.api`, e os testes comparam `meta --json` com `GET /api/meta`.

### 2. CLI como cliente HTTP da API

- **Prós**: Site e CLI dividem o mesmo contador em memória de `RATE_LIMIT_PER_MIN`.
- **Contras**: Exige servidor rodando mesmo para uso local em linha de comando; acopla a CLI ao ciclo de vida da API; adiciona camadas de serialização e erro de conexão.
- **Custo**: Médio (manter cliente HTTP separado, URL/timeout da API e fixture `uvicorn` nos testes).
- **Risco**: Médio: inviabiliza executar a CLI diretamente sem depender do servidor web.

### 3. CLI em modo híbrido (direto por padrão, HTTP quando configurado)

- **Prós**: Suporta os dois cenários.
- **Contras**: Dois caminhos de execução, duas traduções de erro e testes duplicados para manter os dois modos sincronizados.
- **Custo**: Alto.
- **Risco**: Alto: divergência silenciosa entre o modo direto e o modo HTTP.

## Decisão

A CLI é um adaptador de entrada direto sobre o `Container` e `app/services/` (opção 1), mantendo integralmente a paridade funcional e de regras com a API e o site (ADR 0040):

- **Sem cliente HTTP na CLI**: nenhuma dependência de `fastapi`, `uvicorn` ou servidor HTTP rodando.
- **Mesmos serviços e projeções (SSOT)**: `app/services/meta.py`, `BatchSummary`, `RunSummary` e `ComparisonSummary` alimentam tanto `adapters/api/routers.py` quanto `adapters/cli/main.py`.
- **Erros do domínio traduzidos direto**: `ERROR_EXIT_CODES` mapeia `DomainError` diretamente para `0/1/2/3`, de forma simétrica ao `ERROR_STATUS` da API (ADR 0018).
- **Limite por IP**: permanece exclusivo da API HTTP (`POST /api/generate`).

## Por que vence

- **O que ganha e o que perde**: Ganha autonomia completa da CLI no mesmo nível da API, menos código e aderência estrita à arquitetura hexagonal. Perde o compartilhamento do contador `RATE_LIMIT_PER_MIN` entre CLI local e API web.
- **Por que compensa**: Em uso local, o usuário controla o próprio processo via `.env` (`LLM_PROVIDER=fake` ou `openrouter`), enquanto o limite por IP protege especificamente o servidor web público.

## Consequências

- `python -m app.adapters.cli.main ...` funciona diretamente sem subir o `uvicorn`.
- Os testes de subprocesso da CLI executam sem fixture de servidor HTTP.
- `tests/test_architecture.py` impede que `app/adapters/cli` importe `fastapi` ou `app.adapters.api`.

## Como verificar

- `pytest -q tests/test_architecture.py tests/test_cli.py tests/test_cli_comparison.py tests/test_errors_mapping.py`
- Rodar `.venv/bin/python -m app.adapters.cli.main customer list` com a API desligada e observar código de saída `0`.
