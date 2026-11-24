# ADR 0033 · Limite de taxa por IP em janela deslizante, em memória

- **Status**: Aceito (detalha a decisão de limite de taxa do [ADR 0024](0024-deploy.md))
- **Data**: 2026-11-21

## Contexto

Num deploy público sem autenticação, qualquer visitante pode disparar gerações, e cada uma
consome a cota do modelo gratuito (que também é limitada pelo provedor). O ADR 0024 decidiu limitar por IP nas rotas
que chamam o LLM; faltava definir o algoritmo, o que conta como chamada, de onde vem o IP e o que acontece com o valor
`RATE_LIMIT_PER_MIN=0`. A configuração já existia em `Settings` (padrão 10) e não era usada.

## Opções consideradas

### Janela deslizante em memória, por IP, como dependência do FastAPI (`adapters/api/ratelimit.py`)

- **Prós**: Sem dependência nem infraestrutura; recusa de forma exata (nunca mais de N chamadas em qualquer intervalo de
  60 s); `Retry-After` calculado do instante real da chamada mais antiga; relógio injetável deixa os testes sem espera.
- **Contras**: Guarda um instante por chamada aceita (no máximo N por IP); o contador é por processo e zera no
  reinício; exige um único worker.
- **Custo**: Baixo (cerca de 100 linhas e testes).
- **Risco**: Baixo: com `--workers 1`, o limite é exato; com vários workers, o limite efetivo seria N vezes maior.

### Janela fixa por minuto (contador por IP e por minuto)

- **Prós**: Estado mínimo (um inteiro por IP).
- **Contras**: Permite até 2N chamadas em torno da virada do minuto; o `Retry-After` é o resto do minuto, não o tempo
  real até liberar.
- **Custo**: Baixo.
- **Risco**: Médio: a rajada dupla gasta justamente a cota que o limite protege.

### Limite no Caddy ou em outro proxy

- **Prós**: Recusa antes de chegar ao Python; vale para qualquer rota.
- **Contras**: O Caddy padrão não traz limite de taxa (exige módulo extra, compilado à parte); a regra sai do repositório
  e não é testável pelo `pytest`; o proxy não distingue rotas que chamam o LLM sem uma lista duplicada de caminhos.
- **Custo**: Médio.
- **Risco**: Médio: configuração fora do código e dependente do proxy usado.

### Redis (ou outro armazenamento compartilhado)

- **Prós**: Contador único para vários processos e que sobrevive ao reinício.
- **Contras**: Mais um serviço para instalar, proteger e monitorar.
- **Custo**: Médio a alto para uma carga mínima.
- **Risco**: Médio: nova dependência de disponibilidade.

## Decisão

Janela deslizante de 60 s por IP, em memória, aplicada por dependência (`LLM_CALL_LIMIT`) somente a
`POST /api/generate`. O limite aplica-se exclusivamente à borda HTTP (site e clientes da API): a CLI executa o núcleo
diretamente no ambiente local (ADR 0041) e não passa por este contador.

- **O que conta**: cada requisição a `POST /api/generate`, na mesma cota por IP. O modo `all` conta uma vez (embora faça quatro
  chamadas ao modelo) e acertos de cache também contam, porque a rota não sabe de antemão se haverá chamada. Uma
  requisição recusada não entra na janela, então insistir não prolonga o bloqueio. Leituras, `/healthz`, avaliação manual
  e comparações salvas nunca são limitadas.
- **Resposta**: 429 com `{"detail": "Muitas requisições deste endereço; tente de novo em N s."}` e cabeçalho
  `Retry-After: N` (segundos, arredondado para cima, mínimo 1). O front já mostra o `detail` no toast.
- **Valor 0**: desliga o limite. Valor negativo é recusado pelo `Settings`.
- **Origem do IP**: `request.client.host`. O deploy inicia o uvicorn com `--proxy-headers --forwarded-allow-ips
  127.0.0.1`: o uvicorn só lê o `X-Forwarded-For` quando a conexão vem do proxy local e usa o último endereço da cadeia
  que não é confiável (o que o proxy anotou). Medido com o uvicorn real: com `X-Forwarded-For: 7.7.7.7, 9.9.9.9`, o
  cliente é `9.9.9.9`; valores à esquerda, que o visitante pode inventar, não contam. Uma conexão direta de outro
  endereço tem o cabeçalho ignorado (coberto por teste). Atrás de um proxy reverso, portanto, só o `X-Forwarded-For`
  do proxy local é confiável.
- **Memória**: no máximo 10 000 IPs acompanhados; ao passar disso, saem primeiro as chaves vencidas e depois as mais
  antigas.

## Por que vence

- **O que ganha e o que perde**: Ganha proteção exata da cota com código pequeno e testável. Perde o estado
  compartilhado entre processos e entre reinícios.
- **Por que compensa**: O serviço roda com um worker e a carga esperada é mínima; um reinício zera contadores de
  1 minuto, o que não compromete a proteção.

## Consequências

Ao escalar para vários workers ou instâncias, o limite precisa migrar para um armazenamento compartilhado (a interface
`acquire(chave)` de `SlidingWindowLimiter` isola essa troca). Atrás de um CDN ou proxy que reescreva o
`X-Forwarded-For`, é preciso conferir qual endereço chega ao uvicorn; se for o do CDN, o limite passa a ser por
borda e não por visitante.

## Como verificar

`tests/test_ratelimit.py`: janela deslizante com relógio injetado, 429 com `Retry-After` em `/api/generate`, leituras sem
limite, valor 0, IP do proxy confiável e conexão direta com cabeçalho falso. Manual: com `RATE_LIMIT_PER_MIN=1`, o
segundo `curl` a `/api/generate` responde 429.
