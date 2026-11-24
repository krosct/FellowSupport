# Notas de engenharia de prompt

Este documento reúne as estratégias, a arquitetura dos prompts, a evolução entre versões e o que aprendemos ao testar
o **FellowSupport** (assistente de suporte do produto fictício **NuvemPonto**) com avaliações manuais pela rubrica.
As decisões arquiteturais detalhadas estão em [`docs/adr/`](docs/adr/README.md).

## 1. Estratégias e arquitetura de prompt

Em vez de um prompt único e longo, cada versão em `prompts/vN/` separa papel, contexto, adaptação ao perfil, tarefa
por tipo de conteúdo e instrução de reparo ([ADR 0005](docs/adr/0005-prompts-como-arquivos-versionados.md)). O objetivo é
isolar o efeito de cada ajuste e manter saídas JSON estruturadas, verificáveis e sem cadeia de raciocínio exposta.

| Estratégia | Como aplicamos | Onde mora |
|---|---|---|
| Persona e limites | Analista N2 do NuvemPonto; não inventar dados ou telas, não pedir segredos, escalar falhas internas e não expor raciocínio | [`system.md`](prompts/v4/system.md) |
| Contexto delimitado | Perfil do cliente e relato do ticket entre `<ticket>...</ticket>`, instruindo o modelo a tratar o relato apenas como dado | [`context.md`](prompts/v4/context.md) · [ADR 0022](docs/adr/0022-defesa-contra-injecao-de-prompt.md) |
| Adaptação ao perfil | Mapa de `tech_level`, `comm_style` e `channel` separado do texto da tarefa; evoluiu de rótulo cru (`v1`) para guias curtos (`v3`/`v4`) | [`adaptation.json`](prompts/v4/adaptation.json) |
| Decomposição do diagnóstico | Hipóteses ordenadas com probabilidade, fatos a favor/contra, evidências disponíveis, faltantes, conclusão e resumo ao cliente | [`diagnosis.md`](prompts/v4/diagnosis.md) |
| Um prompt por entrega | Quatro geradores independentes em paralelo sobre um núcleo comum, cada um focado em um tipo de saída | [`generators.py`](app/services/generators.py) · [ADR 0007](docs/adr/0007-geradores-independentes.md) |
| Saída estruturada e reparo | Schemas Pydantic estritos (`extra="forbid"`) + regras de canal; se falhar, há uma única retentativa devolvendo o erro exato | [`models.py`](app/domain/models.py) · [`repair.md`](prompts/v4/repair.md) · [ADR 0004](docs/adr/0004-saida-estruturada.md) |
| Fluxograma por código | O modelo devolve apenas nós e arestas de um grafo acíclico; o desenho ASCII é gerado deterministicamente em Python | [`flow_render.py`](app/domain/flow_render.py) · [ADR 0008](docs/adr/0008-fluxograma-ascii-deterministico.md) |
| Versionamento imutável | Pasta `prompts/vN/` travada por `content_sha256` em `meta.json`; a versão mais nova vira padrão | [`registry.py`](app/domain/prompting/registry.py) · [ADR 0006](docs/adr/0006-versoes-de-prompt-imutaveis.md) · [ADR 0039](docs/adr/0039-versao-padrao-e-a-mais-nova.md) |

**Motor e fonte única de limites.** O [`PromptBuilder`](app/domain/prompting/engine.py) lê um snapshot da versão e
renderiza `[system, user]` com `string.Template` em passada única, evitando que `$` no ticket seja reinterpretado.
Os limites dos schemas vivem em [`models.py`](app/domain/models.py) e entram nos templates como variáveis: `diagnosis`
(2 a 3 hipóteses e até 3 faltantes), `resolution_steps` (2 a 6 passos), `clarifying_questions` (2 a 4 perguntas) e
`flow_summary` (3 a 14 nós, rótulos até 100 caracteres, grafo conexo e sem ciclos).

**Canais e segurança.** Uma tabela única em [`channel_rules.py`](app/domain/channel_rules.py) alimenta `$channel_format`
nos prompts e valida o canal `telefone` por código, rejeitando qualquer marca de markdown e acionando reparo. Para
reduzir risco de injeção de prompt ([ADR 0022](docs/adr/0022-defesa-contra-injecao-de-prompt.md)), tags `<ticket>` dentro
do relato viram `[ticket]`, `MAX_TICKET_CHARS` limita o texto a 4.000 caracteres ([`config.py`](app/config.py)) e o
`content_sha256` ([`hash_prompt_version.py`](scripts/hash_prompt_version.py)) compõe a chave SHA-256 do cache
([`cache_key.py`](app/domain/cache_key.py) · [ADR 0010](docs/adr/0010-chave-de-cache.md)).

## 2. Evolução das versões (`v1` a `v4`)

| Versão | Base | O que mudou e por quê | Registro |
|---|---|---|---|
| `v1` | — | Linha de base simples: persona enxuta, rótulos crus em `adaptation.json` e restrição de canal nos 4 tipos | [`prompts/v1/meta.json`](prompts/v1/meta.json) |
| `v2` | `v1` | Explicita que o assistente já é o suporte, exige fatos literais no diagnóstico, proíbe repetir falhas sem contexto, pede `if_it_fails` útil, veta perguntas inacessíveis sem login e pede 1 ação/pergunta por nó `action`/`decision` | [`prompts/v2/meta.json`](prompts/v2/meta.json) |
| `v3` | `v2` | Regras explícitas em `adaptation.json` (`tech_level` e `comm_style`); proíbe inventar telas; evita chutar número de passo em `if_it_fails`; pede rótulos curtos e completos em todos os nós do fluxo e escrita por extenso no `telefone` | [`prompts/v3/meta.json`](prompts/v3/meta.json) |
| `v4` | `v3` | Separa componentes/credenciais distintos (API vs. webhook) em `system.md`; orienta parágrafos curtos em `e-mail` `detalhado` e concisão rígida em `direto`; limita `proceed_note` a 1 frase e `when_to_escalate` a 2 frases; exige relevância real em `evidence_for`/`against` | [`prompts/v4/meta.json`](prompts/v4/meta.json) |

## 3. Protocolo e justiça na comparação

Todas as 35 execuções registradas rodaram com `deepseek/deepseek-v4.1-flash-1017`, `temperature: 0.1`,
`max_tokens: 12000`, `structured_mode: "json_schema"` e `reasoning: "high"`. Das 35 chamadas, 32 concluíram na primeira
tentativa (`attempts: 1`, sem reparo) e 3 falharam por corte do provedor aos 2.400 tokens gastos em raciocínio
([`ae999e929e67`](var/runs/2026-11-23/20261123T211139_ae999e929e67.json),
[`f7c10478132e`](var/runs/2026-11-23/20261123T213447_f7c10478132e.json) e
[`f259d6ff7b8e`](var/runs/2026-11-23/20261123T215453_f259d6ff7b8e.json)).

O comparador em [`comparison.py`](app/domain/comparison.py) recusa comparações injustas ([ADR 0021](docs/adr/0021-comparacao-justa.md)):
exige execuções válidas fora de cache para o mesmo cliente, ticket, tipo, modelo efetivo e parâmetros. A avaliação manual
segue a rubrica fixa de [`rubric.py`](app/domain/rubric.py) ([ADR 0020](docs/adr/0020-rubrica-e-avaliacao-manual.md)):
**clareza**, **adequação ao nível do cliente** e **acionabilidade**, de 1 a 5 (máximo 15; vencedor pela soma,
[ADR 0031](docs/adr/0031-arquivo-de-comparacao-e-vencedor.md)).

## 4. Resultados das três comparações

| Cenário e tipo | `v1` | `v2` | `v3` | `v4` | Vencedora | Arquivo |
|---|---|---|---|---|---|---|
| Dona Marta (`leigo`/`didático`/`telefone`) × `t-2fa` · `diagnosis` | 3/4/3 (**10**) | 4/3/3 (**10**) | 5/5/4 (**14**) | 4/4/3 (**11**) | **`v3`** | [`1b9a078ebad4`](var/comparisons/1b9a078ebad4.json) |
| Rafael (`intermediário`/`detalhado`/`e-mail`) × `t-webhook` · `resolution_steps` | 3/4/4 (**11**) | 4/4/4 (**12**) | 3/5/3 (**11**) | 5/5/5 (**15**) | **`v4`** | [`7e05bdd29f48`](var/comparisons/7e05bdd29f48.json) |
| Bianca (`avançado`/`direto`/`chat`) × `t-webhook` · `clarifying_questions` | 4/4/5 (**13**) | 3/4/4 (**11**) | 4/4/4 (**12**) | 5/5/4 (**14**) | **`v4`** | [`bc0e1e01dafc`](var/comparisons/bc0e1e01dafc.json) |

## 5. O que cada versão melhorou e onde tropeçou

- **`v1` (linha de base).** Acertou o formato básico de telefone graças a `$channel_format`, mas sem regras de papel e
  evidência acabou sugerindo ligar para o próprio suporte em [`8a526ff7c184`](var/runs/2026-11-23/20261123T211141_8a526ff7c184.json),
  misturou suposições e contradições em `H3` ([`e6f966386aa7`](var/runs/2026-11-23/20261123T212202_e6f966386aa7.json))
  e perguntou dado inacessível sem login ([`2dfd13e8a625`](var/runs/2026-11-23/20261123T211146_2dfd13e8a625.json)). Ainda
  assim, no chat da Bianca ([`ca791053a6bc`](var/runs/2026-11-23/20261123T223240_ca791053a6bc.json)) teve o melhor
  `proceed_note` acionável (13/15).
- **`v2` (correções de aderência sem adaptar perfil).** Eliminou alucinações em `evidence_for`/`against`
  ([`8070b06b2460`](var/runs/2026-11-23/20261123T213443_8070b06b2460.json)), tirou o passo redundante de ligar para o
  suporte ([`643f6ea79869`](var/runs/2026-11-23/20261123T213533_643f6ea79869.json)) e melhorou a ordem no passo a passo
  do Rafael ([`44b635b8a21b`](var/runs/2026-11-23/20261123T221630_44b635b8a21b.json)). Em troca, inventou que a tela de
  2FA exibe o telefone ([`323ecdcdfd3d`](var/runs/2026-11-23/20261123T213447_323ecdcdfd3d.json) e
  [`643f6ea79869`](var/runs/2026-11-23/20261123T213533_643f6ea79869.json)),
  apontou do passo 3 para o próprio passo 3, truncou o nó `start` do fluxo aos 100 caracteres
  ([`e07a0b060cd5`](var/runs/2026-11-23/20261123T213503_e07a0b060cd5.json)) e questionou se o staging usa outro token
  ignorando o relato ([`ce799b5b8eb6`](var/runs/2026-11-23/20261123T223250_ce799b5b8eb6.json)).
- **`v3` (adaptação explícita + fluxo completo).** O salto de `adaptation.json` diferenciou bem Rafael e Bianca no mesmo
  ticket e zerou os cortes nos fluxogramas ([`739521e8ce1f`](var/runs/2026-11-23/20261123T215353_739521e8ce1f.json),
  [`4125da356f04`](var/runs/2026-11-23/20261123T215456_4125da356f04.json)). Na Dona Marta
  ([`90947f5a86c4`](var/runs/2026-11-23/20261123T221407_90947f5a86c4.json)) alcançou **14/15** com explicação didática
  clara ("remetentes diferentes do banco"). Porém, em `t-webhook`, confundiu rotação de HMAC do webhook com token da API
  nos passos do Rafael ([`4ae7f7ba0134`](var/runs/2026-11-23/20261123T215405_4ae7f7ba0134.json)), gerou bloco único de
  1.627 caracteres no e-mail do diagnóstico ([`c3e031ffc9ca`](var/runs/2026-11-23/20261123T215401_c3e031ffc9ca.json)) e
  um `proceed_note` de 553 caracteres ([`85108fe06663`](var/runs/2026-11-23/20261123T215355_85108fe06663.json)).
- **`v4` (separação de credenciais e concisão por canal).** Venceu com folga nos cenários técnicos: **15/15** no passo a
  passo do Rafael ([`1a99e703d4b6`](var/runs/2026-11-23/20261123T221658_1a99e703d4b6.json)), separando HMAC do webhook de
  token da API sem perder detalhamento, e **14/15** no chat direto da Bianca
  ([`aba69b5c89e1`](var/runs/2026-11-23/20261123T223302_aba69b5c89e1.json)). Na Dona Marta
  ([`f461b2a23938`](var/runs/2026-11-23/20261123T221327_f461b2a23938.json)), porém, regrediu para 11/15 porque
  `customer_summary` pediu à cliente o número cadastrado no sistema sem ela conseguir logar e citou código por e-mail
  ausente do ticket — mostrando que o ajuste fino precisa ser validado também nos cenários antigos, não só nos novos.

## 6. Decisões e trade-offs

| Decisão | Ganho | Custo / Risco |
|---|---|---|
| Prompts modulares e imutáveis (`string.Template` + `adaptation.json`) | Diff legível e isolamento de cada mudança | Sem lógica condicional dentro dos textos; exige mais arquivos por versão |
| Iteração incremental e cirúrgica (`v1` → `v4`, 1 a 2 linhas por ajuste) | Controla o efeito de cada ajuste sem inflar o prompt | Exige mais rodadas e pode causar regressão pontual em outro cenário |
| Temperatura baixa (`0,1`) e no máximo 1 reparo com o erro ([`repair.md`](prompts/v4/repair.md) · [ADR 0004](docs/adr/0004-saida-estruturada.md)) | Reduz ruído entre versões e evita loops caros (32/32 válidas de 1ª) | Não garante determinismo absoluto e reduz variação em texto aberto |
| Fluxograma ASCII por código ([ADR 0008](docs/adr/0008-fluxograma-ascii-deterministico.md)) | Diagrama alinhado e 100% determinístico | Exige grafo acíclico válido; pode acionar reparo |
| Tabela única em [`channel_rules.py`](app/domain/channel_rules.py) | Prompt e validador nunca divergem | Hoje só `telefone` (sem markdown) tem checagem automática |
| Justiça validada por código e soma simples ([ADR 0021](docs/adr/0021-comparacao-justa.md), [ADR 0031](docs/adr/0031-arquivo-de-comparacao-e-vencedor.md)) | Comparações reproduzíveis e critério uniforme | Empates são mais frequentes e exige rodar tudo no mesmo modelo |

## 7. Limitações conhecidas e próximos passos

- **Amostra pequena e variância.** Cada célula das comparações tem uma única execução (`temperature: 0.1`); diferenças de
  1 ponto cabem no ruído do modelo, e `flow_summary` ainda não passou por comparação avaliada na rubrica.
- **Concorrência de atenção entre regras.** Conforme o prompt acumula instruções (`system.md`, `adaptation.json`, tarefa
  e canal), o modelo às vezes prioriza uma regra nova e relaxa outra — caso da `v4` na Dona Marta
  ([`f461b2a23938`](var/runs/2026-11-23/20261123T221327_f461b2a23938.json)), em que `customer_summary` pediu dado
  inacessível sem login e citou código por e-mail.
- **Sensibilidade ao orçamento de raciocínio.** Com `reasoning: "high"`, instruções densas ou tickets ambíguos elevam o
  gasto silencioso de tokens (chegou a 5.383 em [`4ae7f7ba0134`](var/runs/2026-11-23/20261123T215405_4ae7f7ba0134.json)) e
  levaram o provedor a cortar 3 chamadas aos 2.400 tokens antes do JSON
  ([`ae999e929e67`](var/runs/2026-11-23/20261123T211139_ae999e929e67.json),
  [`f7c10478132e`](var/runs/2026-11-23/20261123T213447_f7c10478132e.json) e
  [`f259d6ff7b8e`](var/runs/2026-11-23/20261123T215453_f259d6ff7b8e.json)).
- **Limitações do sistema.** O cache não tem TTL ([ADR 0028](docs/adr/0028-politica-de-cache.md)), a delimitação
  `<ticket>` reduz mas não elimina injeção de prompt e não há login de usuário final (a proteção limita gerações por IP
  em [ADR 0033](docs/adr/0033-limite-de-taxa-por-ip.md) e exige `ADMIN_API_KEY` para mutações administrativas em
  catálogo e prompts).
- **Próximos passos.** Repetir cada cenário (3 a 5 vezes) para medir variância, avaliar `flow_summary` na rubrica, testar
  `reasoning` moderado mantendo paridade entre versões e corrigir na `v4` (em eventual `v5`) a regra de não pedir dados
  inacessíveis dentro do `customer_summary` do diagnóstico.
