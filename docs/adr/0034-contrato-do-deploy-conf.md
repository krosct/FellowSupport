# ADR 0034 · Contrato do deploy.conf: dados fora das versões, um worker e pacote enxuto

- **Status**: Aceito (detalha a decisão de deploy do ADR 0024)
- **Data**: 2026-11-21

## Contexto

O script de deploy via SSH (systemd de usuário + Caddy com HTTPS) lê um `deploy.conf` com `CHAVE=valor` por linha, sem
executá-lo. Cada versão publicada vai para uma pasta própria (`releases/<id>`, com o link `current` apontando para a
ativa) e o serviço roda dentro dela. Foi preciso decidir onde ficam os dados, quantos workers rodam, o que entra no
pacote e como o modo local se comporta com o `.env`.

## Opções consideradas

### `DATA_DIR={data}`: pasta persistente da VPS, fora das versões

- **Prós**: Histórico, cache e comparações sobrevivem a novos deploys e ao rollback; as versões antigas podem ser
  apagadas sem perder dados; o código das versões é só leitura.
- **Contras**: Os dados passam a depender da pasta da VPS (sem backup automático); a pasta cresce sem expurgo.
- **Custo**: Baixo (uma linha em `SERVICE_ENV`).
- **Risco**: Baixo: copiar a pasta `data/` é o backup completo (ADR 0009: um JSON por execução).

### `DATA_DIR` padrão (`var/` dentro da versão)

- **Prós**: Nenhuma configuração.
- **Contras**: Cada deploy começa com histórico e cache vazios; o rollback volta a uma pasta de dados diferente.
- **Custo**: Nenhum.
- **Risco**: Alto: perda de dados do usuário a cada publicação.

### Um worker (`--workers 1`)

- **Prós**: O limite de taxa por IP em memória é exato (ADR 0033); menor consumo (medido: cerca de 72 MB de RSS após 30
  gerações `all` no modo `fake`, bem abaixo do `MEMORY_MAX=300M`); os endpoints são `def` e rodam no threadpool, então
  uma chamada lenta ao modelo não bloqueia as outras.
- **Contras**: Uma única CPU para o Python; um travamento do processo derruba o serviço até o systemd reiniciar.
- **Custo**: Nenhum.
- **Risco**: Baixo: a carga esperada é mínima e o `Restart=on-failure` religa o serviço.

### Vários workers

- **Prós**: Usa mais núcleos.
- **Contras**: O contador do limite de taxa passa a ser por processo (limite efetivo N vezes maior); mais memória.
- **Custo**: Médio (exigiria armazenamento compartilhado para o limite).
- **Risco**: Médio: o limite deixa de proteger a cota.

### `EXCLUDE` de `docs tests scripts samples .github frontend/src PROMPT_ENGINEERING_NOTES.md`

- **Prós**: Pacote enxuto, só com o que o servidor lê (`app/`, `catalog/`, `prompts/`,
  `requirements.txt`, `deploy.conf` e `frontend/dist`); menos superfície na VPS.
- **Contras**: Quem entra na VPS não encontra a documentação nem os testes.
- **Custo**: Baixo.
- **Risco**: Baixo: um teste (`tests/test_deploy_conf.py`) falha se o `EXCLUDE` cobrir o `INCLUDE` ou uma pasta de execução.

### Enviar o repositório inteiro

- **Prós**: Nada a manter na lista.
- **Contras**: Leva testes, docs e fontes do front que o servidor não usa.
- **Custo**: Nenhum.
- **Risco**: Baixo, mas com pacote maior e mais arquivos expostos.

## Decisão

- `SERVICE_ENV="DATA_DIR={data} PUBLIC_URL={url} PYTHONUNBUFFERED=1"`; `RUN` com `--host 127.0.0.1`, `--workers 1`,
  `--proxy-headers`, `--forwarded-allow-ips 127.0.0.1` e `--no-server-header`; `EXCLUDE` como acima.
- `INSTALL` usa só `requirements.txt` (sem pytest, ruff nem httpx), com Python 3.12 gerenciado pelo `uv` (ADRs 0001 e 0017).
- `REQUIRED="ADMIN_API_KEY"`: o deploy para antes de alterar qualquer coisa se a chave administrativa faltar no `.env` enviado e na VPS. `OPENROUTER_API_KEY` fica vazia no deploy para cada usuário inserir a sua na sessão (`X-OpenRouter-Key`).
- `PUBLIC_PATHS` não é usado: o site precisa de todos os caminhos (`/`, `/api/*`, `/healthz`).
- **`DEV` (modo local)**: reaproveita a `.venv` existente (um `uv venv` incondicional a recriaria e apagaria as
  dependências de desenvolvimento) e lê a porta de `PORT`, com o mesmo padrão do `Settings` (um teste confere a igualdade).

## Por que vence

- **O que ganha e o que perde**: Ganha persistência dos dados entre versões, limite de taxa exato e um pacote mínimo.
  Perde a escala horizontal e a conveniência de ter docs e testes na VPS.
- **Por que compensa**: O serviço tem carga mínima e o objetivo do ponto extra é um deploy funcional e seguro para a cota.

## Consequências

- O modo `local` exporta todas as chaves do `.env` para o processo, e elas **prevalecem** sobre variáveis já definidas
  no shell: `LLM_PROVIDER=fake deploy.sh local` não surte efeito com um `.env` em `openrouter`. Para ensaiar sem gastar
  cota, o `.env` precisa de `LLM_PROVIDER=fake` (e o `REQUIRED` também vale no modo local, então `ADMIN_API_KEY` precisa
  de algum valor).
- O primeiro deploy envia o `.env` do projeto (ou `--env ARQUIVO`); o `.env` nunca vai no pacote, e as chaves enviadas
  substituem as da VPS.
- Os dados não têm expurgo automático: com o uso, `data/runs` e `data/cache` crescem e precisam de limpeza manual.

## Como verificar

`tests/test_deploy_conf.py` (contrato do arquivo). Manual: `deploy.sh local` num clone com `.env` de teste (`/healthz`
e `/` com 200 e uma geração `fake`); o pacote montado pela mesma lógica do script traz `frontend/dist` e não traz
`.env`, `var/` nem `node_modules`; uma versão extraída e instalada só com `requirements.txt` sobe com `DATA_DIR`
em outra pasta e grava ali as execuções.
