# ADR 0024 · Deploy via script SSH, systemd de usuário e Caddy

- **Status**: Aceito
- **Data**: 2026-11-20

## Contexto

O deploy público é um ponto extra do PDF. A aplicação precisa de um serviço persistente, HTTPS e proteção da cota gratuita do LLM.

## Opções consideradas

### Script de deploy via SSH que instala um serviço systemd de usuário atrás de Caddy, com build local do front, inclusão de `frontend/dist` no pacote, verificação de `/healthz` e limite de taxa por IP em memória nos endpoints que chamam o LLM

- **Prós**: Sem Docker nem Node no servidor; HTTPS automático pelo Caddy; reinício automático pelo systemd; build reproduzível localmente.
- **Contras**: Exige servidor com SSH, systemd e Caddy; limite de taxa em memória não é compartilhado entre processos.
- **Custo**: Baixo a médio: servidor e domínio.
- **Risco**: Médio: exposição pública consome cota; mitigado pelo limite de taxa.

### Contêiner Docker em plataforma gerenciada (PaaS)

- **Prós**: Padrão amplo e escalável.
- **Contras**: Imagem a manter, custo da plataforma e disco efêmero para `var/`.
- **Custo**: Médio a alto.
- **Risco**: Médio: perda de dados em disco efêmero.

### Hospedar front e API separados

- **Prós**: Escala independente.
- **Contras**: CORS e duas configurações (ver ADR 0012).
- **Custo**: Médio.
- **Risco**: Médio.

## Decisão

Script de deploy via SSH que instala serviço systemd de usuário atrás de Caddy, com build local do front e inclusão de `frontend/dist` no pacote.

## Por que vence

- **O que ganha e o que perde**: Ganha um deploy simples, barato e verificável. Perde a elasticidade de uma plataforma gerenciada.
- **Por que compensa**: Compensa porque a carga esperada é mínima e o extra do PDF pede apenas um deploy funcional.

## Consequências

O `deploy.conf` declara aplicação, build, inclusão do front, instalação, comando, rota de saúde e variável obrigatória. O limite de taxa vive em `adapters/api/ratelimit.py`.

## Como verificar

Execução local do script de deploy sobe o serviço e `GET /healthz` retorna 200; teste do limite de taxa (excesso retorna 429).
