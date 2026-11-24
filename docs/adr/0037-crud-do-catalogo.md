# ADR 0037 · CRUD de clientes e tickets direto nos arquivos de `catalog/`

- **Status**: Aceito
- **Data**: 2026-11-23

## Contexto

Clientes (`catalog/profiles.json`) e tickets (`catalog/tickets.json`) eram arquivos versionados, só de leitura.
O pedido é um CRUD simples de cada um, em abas próprias (Cliente e Ticket), que altere **esses** arquivos e mais
nenhum. A aba Gerar só escolhe cliente e ticket. As execuções guardam cópia do cliente e do ticket usados
(`customer_profile` e `RunTicket`), então remover um item não quebra o histórico.

## Opções consideradas

### 1. Onde gravar

#### Nos próprios arquivos de `catalog/` (decisão pedida)

- **Prós**: Uma fonte só, a que o CLI, os scripts e os testes já leem; o que se vê na interface é o que está em
  `catalog/`; sem cópia nem semente.
- **Contras**: Usar a interface altera arquivos versionados (o `git status` mostra); o deploy empacota `catalog/` a
  partir do git, então na VPS os itens criados lá são sobrescritos pelo catálogo versionado a cada deploy e os de lá
  não voltam ao git; testes que usam o catálogo real passariam a escrever nele.
- **Custo**: Baixo.
- **Risco**: Médio: perda dos itens da VPS num deploy novo e escrita acidental em testes (mitigada abaixo).

#### Cópia editável em `var/` (adotada e depois descartada)

- **Prós**: Não suja o git; sobrevive ao deploy.
- **Contras**: Duas fontes para o mesmo dado; mudanças no catálogo versionado não chegam a quem já tem a cópia;
  contraria o pedido de editar só `catalog/`.
- **Custo**: Médio.
- **Risco**: Baixo, mas com dado divergente.

### 2. Identificador do item novo

#### Prefixo e 8 hexadecimais gerados no servidor (`c-` cliente, `t-` ticket)

- **Prós**: Estável (execuções e cache apontam para ele); independe do nome, que pode ser editado; segue os
  prefixos dos exemplos.
- **Contras**: Não legível; colisão possível em teoria (2^32), recusada pelo armazenamento.
- **Custo**: Baixo.
- **Risco**: Baixo.

#### Slug do nome ou do título

- **Prós**: Legível.
- **Contras**: Editar o nome deixaria o id desatualizado ou o mudaria, quebrando referências; nomes repetidos colidem.
- **Custo**: Baixo.
- **Risco**: Médio.

## Decisão

- `JsonProfileRepo` e `JsonTicketRepo` (base comum `_JsonCatalog`) leem **e** gravam `catalog/profiles.json` e
  `catalog/tickets.json`. Cada operação relê o arquivo, altera e grava de forma atômica; um `Lock` serializa
  ler-alterar-gravar (o serviço roda em threads, ADR 0015). Portas `ProfileStore` e `TicketStore` (leitura de
  `*Repo` mais `add`, `update` e `remove`); os geradores continuam dependendo só da leitura.
- `services/catalog.py` valida: textos sem espaços nas pontas e não vazios; nome até `PROFILE_NAME_MAX_CHARS` (60),
  título até `TICKET_TITLE_MAX_CHARS` (120), corpo até `max_ticket_chars`; no máximo `MAX_CATALOG_PROFILES` (20) e
  `MAX_CATALOG_TICKETS` (100) itens (contra crescimento sem fim numa instalação pública). Id gerado no servidor.
- API: `POST /api/profiles|tickets` (201), `PUT` e `DELETE /api/profiles|tickets/{id}` (devolvem o item). Validação
  responde 422 (enums desconhecidos, texto vazio ou longo) e id inexistente 404. `/api/meta` traz
  `limits.max_ticket_title_chars` e `limits.max_profile_name_chars`; `free_ticket_title` saiu (o site não o usa).
- Testes: o fixture `settings` usa uma **cópia** de `catalog/` em pasta temporária, então nenhum teste escreve no
  catálogo real (`tests/test_catalog_crud.py` confere que o arquivo real fica intacto).
- Site: abas **Cliente** e **Ticket** antes de Gerar, cada uma com lista (Editar e Remover por item) e formulário
  (Adicionar ou Editar, com Cancelar edição). Remover pede confirmação numa janela própria (`ConfirmDialog`, a base
  da confirmação do cache, ADR 0036). O formulário só grava pelo botão; trocar de aba mantém o rascunho. Gerar só
  escolhe, e abas Gerar e Comparar passam a outro item se o escolhido for removido.

## Por que vence

- **O que ganha e o que perde**: Ganha uma fonte única, editável pela interface. Perde o isolamento do git: o catálogo
  versionado muda com o uso e, na VPS, os itens criados não sobrevivem a um deploy novo.
- **Por que compensa**: É o comportamento pedido, e o custo (deploy) é conhecido e restrito a quem edita na VPS.

## Consequências

- Em ambiente local sem `ADMIN_API_KEY`, mutações ficam abertas; em deploy (`PUBLIC_URL` definida) ou com `ADMIN_API_KEY` configurada, `POST`, `PUT` e `DELETE` exigem o cabeçalho `X-Admin-Key` (informado na sessão pelo diálogo de chaves). Os limites de quantidade restringem o crescimento do catálogo.
- Quem quiser manter os itens criados deve versionar as mudanças de `catalog/` antes do deploy.
- Testes: `tests/test_catalog_crud.py`.
