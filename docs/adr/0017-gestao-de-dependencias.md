# ADR 0017 · uv e requirements.txt com versões fixadas

- **Status**: Aceito
- **Data**: 2026-11-20

## Contexto

O PDF exige `requirements.txt`. É preciso instalar rápido, reproduzir ambientes e gerenciar a versão do Python.

## Opções consideradas

### `uv` com `requirements.txt` (produção) e `requirements-dev.txt` (pytest, ruff, httpx), versões fixadas

- **Prós**: Instalação muito rápida; compatível com pip; cumpre o PDF; o script de deploy usa o mesmo arquivo.
- **Contras**: Sem lock de dependências transitivas; `uv` precisa estar instalado (ou usar pip).
- **Custo**: Baixo.
- **Risco**: Baixo: dependências diretas fixadas reduzem a deriva.

### `pyproject.toml` com `uv.lock`

- **Prós**: Lock completo e reprodutibilidade rigorosa.
- **Contras**: Ainda seria preciso exportar para `requirements.txt` para cumprir o PDF e o deploy; dois formatos para manter.
- **Custo**: Médio.
- **Risco**: Médio: divergência entre lock e requirements.

### pip puro com venv

- **Prós**: Sem ferramenta extra.
- **Contras**: Resolução mais lenta e sem gestão da versão do Python.
- **Custo**: Baixo.
- **Risco**: Baixo.

## Decisão

Usar `uv` para criar o ambiente e instalar, com `requirements.txt` e `requirements-dev.txt` de versões fixadas. O README documenta também o caminho com pip.

## Por que vence

- **O que ganha e o que perde**: Ganha velocidade e simplicidade. Perde o lock transitivo completo.
- **Por que compensa**: Compensa porque o requisito do PDF é `requirements.txt`, e o pip funciona como alternativa.

## Consequências

Atualizações de versão viram commits próprios com testes passando.

## Como verificar

`uv venv .venv --python 3.12 && uv pip install -r requirements-dev.txt` conclui sem erro e `pytest -q` passa.
