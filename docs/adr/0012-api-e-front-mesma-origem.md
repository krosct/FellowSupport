# ADR 0012 · FastAPI serve a API em /api e o front em /

- **Status**: Aceito
- **Data**: 2026-11-20

## Contexto

O front-end React precisa conversar com a API e ser publicado de forma simples, com um único deploy.

## Opções consideradas

### FastAPI serve `/api` e os arquivos estáticos de `frontend/dist` em `/`, na mesma origem; em desenvolvimento, o proxy do Vite encaminha `/api` e `/healthz`

- **Prós**: Sem CORS; um processo, um serviço, uma URL; deploy simples.
- **Contras**: Acopla o ciclo de release do front ao do back; é preciso gerar o build antes de rodar em produção.
- **Custo**: Baixo.
- **Risco**: Baixo: sem `frontend/dist`, a API funciona normalmente e só `/` fica indisponível.

### Front hospedado separadamente

- **Prós**: Escala e publica o front de forma independente em CDN.
- **Contras**: CORS, duas URLs, dois deploys e configuração de domínio duplicada.
- **Custo**: Médio.
- **Risco**: Médio: erros de CORS e de versões divergentes.

### Renderização no servidor (templates)

- **Prós**: Sem build de front.
- **Contras**: Interface menos interativa; descarta o ecossistema React.
- **Custo**: Médio.
- **Risco**: Baixo.

## Decisão

Mesma origem: a API monta `frontend/dist` em `/` quando a pasta existe.

## Por que vence

- **O que ganha e o que perde**: Ganha simplicidade operacional. Perde a independência de release do front.
- **Por que compensa**: Compensa porque o escopo é pequeno e o ponto extra de deploy é mais fácil com um único serviço.

## Consequências

Rotas de API sempre com prefixo `/api`, exceto `/healthz`. O build do front é gerado localmente e empacotado.

## Como verificar

Teste do `TestClient` para `/api/*` e `/healthz`; com `frontend/dist` presente, `GET /` devolve o HTML do build.
