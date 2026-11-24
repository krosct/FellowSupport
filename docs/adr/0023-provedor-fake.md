# ADR 0023 · Provedor fake para rodar sem chave

- **Status**: Aceito
- **Data**: 2026-11-20

## Contexto

Quem avalia o projeto precisa executá-lo mesmo sem chave de API ou com o modelo gratuito fora do ar.

## Opções consideradas

### `LLM_PROVIDER=openrouter|fake`, com `fake` como padrão: respostas determinísticas e válidas por schema

- **Prós**: O projeto inteiro roda offline; testes e demonstração sem custo; falha de modelo não bloqueia a avaliação.
- **Contras**: As respostas do fake não refletem qualidade real de modelo.
- **Custo**: Baixo.
- **Risco**: Baixo: a interface indica o provedor usado em cada execução.

### Exigir chave sempre

- **Prós**: Sem código extra.
- **Contras**: O avaliador não consegue executar sem credenciais ou com cota esgotada.
- **Custo**: Baixo.
- **Risco**: Alto.

### Gravar respostas reais e reproduzi-las

- **Prós**: Respostas realistas offline.
- **Contras**: Cobre só cenários gravados; manutenção das gravações.
- **Custo**: Médio.
- **Risco**: Médio.

## Decisão

Adicionar o provedor `fake` como padrão de `Settings`. O adaptador real só é criado com `LLM_PROVIDER=openrouter` e chave presente.

## Por que vence

- **O que ganha e o que perde**: Ganha executabilidade garantida. Perde realismo das respostas no modo fake.
- **Por que compensa**: Compensa porque garante que qualquer pessoa consiga instalar e executar o fluxo completo localmente seguindo apenas o README, sem depender de credenciais externas.

## Consequências

Cada execução registra `provider`, evitando confundir amostras fake com reais.

## Como verificar

Subir a API sem `.env` funciona; configurar `openrouter` sem chave falha com mensagem clara.
