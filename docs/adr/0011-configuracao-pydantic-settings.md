# ADR 0011 · Configuração com pydantic-settings

- **Status**: Aceito
- **Data**: 2026-11-20

## Contexto

A aplicação tem mais de 20 variáveis (provedor, modelo, limites, pastas, servidor) e uma chave secreta que nunca pode vazar em logs ou respostas.

## Opções consideradas

### `pydantic-settings` em `app/config.py`, com `SecretStr` para a chave

- **Prós**: Tipos e validação na carga; `SecretStr` oculta a chave no repr; fonte única de configuração e padrões.
- **Contras**: Uma dependência a mais (pequena, do mesmo ecossistema do Pydantic).
- **Custo**: Baixo.
- **Risco**: Baixo: erro de configuração aparece cedo, na inicialização.

### `os.getenv` espalhado pelo código

- **Prós**: Nenhuma dependência.
- **Contras**: Sem tipos nem validação; valores padrão repetidos; viola a regra de fonte única; fácil vazar o segredo.
- **Custo**: Baixo no início.
- **Risco**: Alto: inconsistência e vazamento.

### `python-dotenv` sozinho

- **Prós**: Carrega o `.env` com pouco código.
- **Contras**: Não valida nem converte tipos; não oculta segredos.
- **Custo**: Baixo.
- **Risco**: Médio: erros de tipo em tempo de execução.

## Decisão

Classe `Settings` com `pydantic-settings`, lendo o `.env`, com provedor padrão `fake` e `OPENROUTER_API_KEY` como `SecretStr`.

## Por que vence

- **O que ganha e o que perde**: Ganha tipagem, validação e proteção do segredo. Perde a menor dependência possível.
- **Por que compensa**: Compensa porque configuração tipada e segura é parte do critério de implementação técnica do PDF.

## Consequências

Nenhum outro módulo lê variáveis de ambiente diretamente. Os nomes das variáveis são os do `.env.example`.

## Como verificar

Teste: o repr e o `model_dump` não contêm a chave; sem `.env`, os padrões carregam com provedor `fake`.
