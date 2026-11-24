# ADR 0043 · Log de eventos em JSON Lines na raiz do projeto

- **Status**: Aceito (amplia o ADR 0019)
- **Data**: 2026-11-23

## Contexto

O ADR 0019 deixou a observabilidade no JSON de cada execução e no `logging` padrão no terminal. Para investigar
falhas intermitentes (por exemplo, um tipo que falha só no modo `all`), é preciso ver em sequência, num lugar só,
cada geração, o lote a que ela pertence, as chamadas ao LLM, as avaliações e as comparações. Os JSONs ficam
espalhados por dia, e o log do terminal se perde e não é estruturado (a CLI nem o configura).

## Opções consideradas

### Porta `EventLog` e adaptador JSON Lines em `fellowsupport.log` (escolhida)

- **Prós**: Um evento por linha, legível com `tail -f`, `grep` e `jq`. O núcleo só conhece a porta (testes usam `NullEventLog`). API e CLI gravam no mesmo arquivo porque o `container` é comum. A escrita é por acréscimo (`O_APPEND`, um `write` por linha, com lock entre threads), então as linhas não se misturam.
- **Contras**: Não há rotação: o arquivo cresce (cerca de 1 KB por geração).
- **Custo**: Baixo: um módulo de porta, um adaptador e a variável `LOG_FILE`.
- **Risco**: Baixo: falha de disco no log só gera um aviso e nunca derruba a geração.

### `logging` padrão com `FileHandler` e mensagens em texto

- **Prós**: Sem código novo de escrita; rotação pronta com `RotatingFileHandler`.
- **Contras**: Mensagens em texto livre são difíceis de filtrar e agregar. Campos aninhados (chamadas, notas) não cabem bem. Configurar o handler global em cada ponto de entrada duplica código entre API e CLI.
- **Custo**: Baixo.
- **Risco**: Médio: o formato tende a divergir entre os pontos que registram.

### OpenTelemetry com coletor

- **Prós**: Rastreamento e métricas padronizados.
- **Contras**: Dependências e infraestrutura desproporcionais ao escopo (o mesmo motivo do ADR 0019).
- **Custo**: Alto.
- **Risco**: Médio.

## Decisão

Criar `app/ports/events.py` (porta `EventLog`, nomes dos eventos e `NullEventLog`) e
`app/adapters/storage/event_log.py` (`JsonLinesEventLog`), ligados no `container` com `LOG_FILE` (padrão
`fellowsupport.log` na raiz, ignorado pelo git, permissão 600). Eventos:

- `generation`: uma linha por execução gravada (sucesso, erro ou acerto de cache), com perfil, ticket (id, título e tamanho, sem o texto), versão e hash do prompt, modelo pedido e efetivo, parâmetros, cache, tentativas, latência, uso, `llm_calls`, erro, `batch_id` e caminho do JSON.
- `generation_batch`: o modo `all`, com o desfecho de cada tipo, os tipos que falharam e o uso somado.
- `evaluation`: notas, justificativas e total de cada execução avaliada (avulsa ou dentro de uma comparação).
- `comparison`: cenário, versões com total, vencedor, conclusão e caminho do JSON.

## Por que vence

- **O que ganha e o que perde**: Ganha uma linha do tempo estruturada e única para toda a aplicação. Perde a rotação automática.
- **Por que compensa**: O volume é baixo (uma linha por ação do usuário) e o formato permite consultas como "todas as falhas por provedor" com um único `jq`.

## Consequências

- O texto do ticket e a saída gerada não vão para o log (ADR 0019); o `run_id` e o `saved_path` levam ao JSON completo.
- Os testes redirecionam `LOG_FILE` para a pasta temporária de cada teste.
- Se o arquivo crescer demais, a rotação pode ser feita fora da aplicação (`logrotate`) sem mudar o código.

## Como verificar

`pytest -q tests/test_observability.py`. Na prática: gerar com `LLM_PROVIDER=fake ... generate --type all` e
rodar `jq -c 'select(.event=="generation_batch")' fellowsupport.log`.
