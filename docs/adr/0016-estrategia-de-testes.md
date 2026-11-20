# ADR 0016 · Testes: pytest, LLM falso e TestClient

- **Status**: Aceito
- **Data**: 2026-11-20

## Contexto

Os testes precisam ser rápidos, determinísticos, gratuitos e rodar sem rede. Chamadas reais a modelos gratuitos são instáveis e consomem cota.

## Opções consideradas

### pytest + `FakeLLM` (adaptador da porta) + `TestClient` do FastAPI; adaptador OpenAI testado com `httpx.MockTransport`; chamadas reais só em script manual

- **Prós**: Suíte determinística e gratuita; cobre API, CLI, domínio e adaptador sem rede.
- **Contras**: O LLM falso não prova a qualidade real das respostas; exige um teste de fumaça manual à parte.
- **Custo**: Baixo.
- **Risco**: Baixo: a lacuna é coberta por `scripts/smoke_llm.py`.

### Usar `respx` para simular HTTP

- **Prós**: API de simulação rica.
- **Contras**: Dependência extra quando `httpx.MockTransport` já resolve.
- **Custo**: Baixo.
- **Risco**: Baixo.

### Chamadas reais ao LLM nos testes

- **Prós**: Valida o comportamento de ponta a ponta.
- **Contras**: Instável, lenta, consome cota gratuita e quebra sem chave.
- **Custo**: Alto.
- **Risco**: Alto: falhas intermitentes no CI.

### Sem testes automatizados

- **Prós**: Menos trabalho.
- **Contras**: Perde pontos de extras e de implementação; regressões invisíveis.
- **Custo**: Baixo no início.
- **Risco**: Alto.

## Decisão

pytest com `FakeLLM`, `TestClient` e `httpx.MockTransport`; teste real separado e manual.

## Por que vence

- **O que ganha e o que perde**: Ganha confiabilidade e custo zero. Perde a validação automática de qualidade real do modelo.
- **Por que compensa**: Compensa porque a qualidade do modelo é avaliada pela rubrica, não por testes unitários.

## Consequências

Os testes usam diretórios temporários (`tmp_path`) e nunca escrevem em `var/` real.

## Como verificar

`pytest -q` passa sem rede e sem chave; `ruff check .` limpo.
