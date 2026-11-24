# ADR 0036 · Confirmação antes de substituir entradas do cache

- **Status**: Aceito (complementa o [ADR 0035](0035-cache-grava-sempre.md))
- **Data**: 2026-11-23

## Contexto

Pelo ADR 0035, gerar sem consultar o cache (`use_cache=false`, `--no-cache`, caixa desmarcada) grava o resultado e
troca a origem da chave. A troca descarta uma entrada que o usuário pode querer manter, e uma geração real gasta
cota. O pedido é avisar antes, num único ponto, para qualquer cliente (API, CLI e site): se algum item do pedido
substituir uma entrada existente, nada é gerado até o usuário confirmar, e a confirmação cobre todos os itens de uma
vez (os quatro tipos do modo `all`).

## Opções consideradas

### 1. Onde a confirmação é garantida

#### No serviço, com `confirm_replace` e erro de domínio (409 na API, flag na CLI)

- **Prós**: Uma regra só para API, CLI e site; vale também para scripts; a checagem roda antes de qualquer geração,
  sem janela de corrida entre "perguntar" e "gerar"; o cliente repete o mesmo pedido com `confirm_replace=true`.
- **Contras**: Quem já usava `use_cache=false` sobre entradas existentes passa a receber 409 até enviar o campo novo;
  o pedido de confirmação conta no limite de taxa por IP (a rota não distingue).
- **Custo**: Médio (guarda no serviço, DTOs, flag da CLI, tratador do 409, tratamento no front).
- **Risco**: Baixo: o campo tem padrão `false`; testes e clientes antigos mudam em um ponto.

#### Endpoint de consulta e janela só no site

- **Prós**: A API e os testes atuais ficam iguais.
- **Contras**: API e CLI não são protegidas; há janela de corrida entre a consulta e a geração; a regra fica no cliente.
- **Custo**: Médio.
- **Risco**: Médio: comportamento diferente por cliente.

### 2. O que conta como substituição

#### Só entrada utilizável (origem existente, bem-sucedida e com saída)

- **Prós**: Não pergunta quando nada se perde (ponteiro órfão, apontando para erro, ou chave sem entrada); a primeira
  geração com `use_cache=false` não pede confirmação.
- **Contras**: Exige reaproveitar a mesma verificação do acerto de cache (já existe: `_find_cached_source`).
- **Custo**: Baixo.
- **Risco**: Baixo.

#### Qualquer ponteiro existente

- **Prós**: Regra mais simples de explicar.
- **Contras**: Pergunta por entradas que o cache já ignora.
- **Custo**: Baixo.
- **Risco**: Baixo, com atrito inútil.

## Decisão

- `generate` e `generate_all` recebem `confirm_replace` (padrão `false`). Com
  `use_cache` ligado ou `confirm_replace` verdadeiro, nada é verificado. Com `use_cache` desligado, antes de gerar
  qualquer item, o serviço lista **todos** os itens do pedido que trocariam uma entrada utilizável e, havendo algum,
  levanta `CacheReplaceRequired` com a lista completa (`CacheConflict`: tipo, versão, execução de origem atual e data).
  Nada é gerado nem gravado.
- A chave de cache vem de uma só função (`_cache_key`), usada pela geração e pela verificação.
- API: HTTP 409 com `{detail, code: "cache_replace_required", conflicts: [...]}`; o cliente repete o mesmo pedido com
  `confirm_replace: true`. CLI: exit code 1, lista as entradas e orienta a repetir com `--confirm-replace`.
- Site: a janela é um `<dialog>` próprio (sem `confirm` nativo), com a lista inteira e os botões "Cancelar" e
  "Substituir e continuar"; cancelar (botão, Esc ou clique fora) devolve a tela ao estado anterior, sem perder o
  resultado já exibido. Vale para a aba Gerar (inclusive "Todos").

## Por que vence

- **O que ganha e o que perde**: Ganha uma proteção única, antes do gasto de cota e sem corrida. Perde a
  compatibilidade com quem usava `use_cache=false` sobre entradas existentes sem o campo novo.
- **Por que compensa**: O 409 traz tudo o que será trocado, e a mudança do cliente é um campo.

## Consequências

- O 409 conta no limite de taxa por IP (uma requisição a mais por confirmação).
- Entre a verificação e a geração outra execução pode gravar a mesma chave; a confirmação vale para o estado visto.
- Testes: `tests/test_cache.py`, `tests/test_api_generate.py` e `tests/test_cli.py`.
