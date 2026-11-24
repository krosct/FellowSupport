# ADR 0039 · A versão padrão do prompt é sempre a mais nova

- **Status**: Aceito (a versão padrão deixa de ser configuração; complementa os ADRs 0006 e 0014)
- **Data**: 2026-11-23

## Contexto

A versão usada quando ninguém escolhe (API, CLI, seletor da aba Gerar e selo "padrão") vinha da variável
`DEFAULT_PROMPT_VERSION`, fixada em `v1`. Cada versão nova (v2, v3) exigia lembrar de mudar a variável; esquecer
deixava as novas gerações na linha de base, sem as regras de adaptação. A variável também era um segundo lugar que
precisava concordar com a pasta `prompts/`.

## Opções consideradas

### Manter `DEFAULT_PROMPT_VERSION` e atualizá-la a cada versão

- **Prós**: Permite fixar uma versão antiga em produção; nenhuma mudança de código.
- **Contras**: Passo manual esquecível; duas fontes de verdade (variável e pasta); valor inexistente só falha na
  primeira geração.
- **Custo**: Nenhum agora; um lembrete a cada versão.
- **Risco**: Médio: gerações e comparações saem com a versão errada sem aviso.

### A mais nova do registro é a padrão (escolhida)

- **Prós**: Fonte única (`PromptRegistry.latest()`, que ordena numericamente `v2 < v10`); criar a pasta `vN` já a
  torna padrão; API, CLI e front concordam sem configuração.
- **Contras**: Publicar uma versão nova muda o comportamento de quem não pede versão; não há como fixar uma antiga
  por configuração (quem precisa informa `prompt_version` ou `--version`).
- **Custo**: Baixo: remover a variável e três usos; o cache já separa versões pelo hash do prompt, então nada antigo
  é reaproveitado por engano.
- **Risco**: Baixo: execuções passadas guardam a própria `prompt_version`.

### Campo `default: true` no `meta.json`

- **Prós**: Permite escolher qualquer versão como padrão.
- **Contras**: `meta.json` é imutável (ADR 0006); o campo teria de mudar na versão anterior ao promover a nova.
- **Custo**: Médio. **Risco**: Alto: viola a imutabilidade.

## Decisão

`PromptRegistry.latest()` devolve a maior versão; é o padrão em geração, CLI (`versions`, `generate`), smoke e
`GET /api/prompt-versions` (`is_default`) e `GET /api/meta` (`default_prompt_version`). A variável foi removida.
O seletor da aba Gerar começa nela.

## Verificação

Testes do registro (`latest`, ordenação numérica, registro vazio) e da API (`is_default` só na maior versão).
