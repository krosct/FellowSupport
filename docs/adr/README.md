# Registro de decisões de arquitetura (ADRs)

Cada ADR registra uma decisão técnica vigente do projeto, as alternativas comparadas (com prós, contras, custo e risco) e como verificá-la. Decisões que deixaram de existir foram removidas ou consolidadas para manter este registro consistente com a base atual; números cujas decisões saíram do escopo ficam marcados como `Aposentado` (caso do `0030`) para preservar a estabilidade da numeração subsequente.

## Índice

| Nº | Decisão | Status |
|---|---|---|
| [0001](0001-python-3-12.md) | Python 3.12 fixado em .python-version | Aceito |
| [0002](0002-arquitetura-hexagonal.md) | Arquitetura hexagonal (Ports and Adapters) | Aceito |
| [0003](0003-sdk-openai-com-openrouter.md) | SDK openai com base_url do OpenRouter | Aceito |
| [0004](0004-saida-estruturada.md) | Saída estruturada com schema Pydantic e reparo | Aceito |
| [0005](0005-prompts-como-arquivos-versionados.md) | Prompts como arquivos versionados com string.Template | Aceito |
| [0006](0006-versoes-de-prompt-imutaveis.md) | Versões de prompt imutáveis com hash de conteúdo | Aceito |
| [0007](0007-geradores-independentes.md) | Quatro geradores independentes sobre um núcleo comum | Aceito |
| [0008](0008-fluxograma-ascii-deterministico.md) | Fluxograma: árvore de decisão em JSON e ASCII gerado por código | Aceito |
| [0009](0009-persistencia-json-por-execucao.md) | Persistência em JSON, um arquivo por execução | Aceito |
| [0010](0010-chave-de-cache.md) | Chave de cache canônica com SHA-256 | Aceito |
| [0011](0011-configuracao-pydantic-settings.md) | Configuração com pydantic-settings | Aceito |
| [0012](0012-api-e-front-mesma-origem.md) | FastAPI serve a API em /api e o front em / | Aceito |
| [0013](0013-react-vite-pico.md) | React + Vite (JavaScript) + Pico CSS | Aceito |
| [0014](0014-constantes-via-api-meta.md) | Constantes do domínio servidas por GET /api/meta | Aceito |
| [0015](0015-nucleo-sincrono.md) | Núcleo síncrono com endpoints def | Aceito |
| [0016](0016-estrategia-de-testes.md) | Testes: pytest, LLM falso e TestClient | Aceito |
| [0017](0017-gestao-de-dependencias.md) | uv e requirements.txt com versões fixadas | Aceito |
| [0018](0018-erros-do-dominio.md) | Exceções do domínio mapeadas para HTTP e CLI | Aceito |
| [0019](0019-observabilidade-leve.md) | Observabilidade leve com logging e métricas por execução | Ampliado (0043) |
| [0020](0020-rubrica-e-avaliacao-manual.md) | Rubrica em constante única e avaliação manual | Aceito |
| [0021](0021-comparacao-justa.md) | Comparação justa garantida por código | Aceito |
| [0022](0022-defesa-contra-injecao-de-prompt.md) | Defesa contra injeção de prompt pelo ticket | Aceito |
| [0023](0023-provedor-fake.md) | Provedor fake para rodar sem chave | Aceito |
| [0024](0024-deploy.md) | Deploy via script SSH, systemd de usuário e Caddy | Aceito |
| [0025](0025-idioma-e-fuso.md) | Idioma pt-BR e horários com fuso configurado | Aceito |
| [0026](0026-modelo-padrao.md) | Modelo padrão de geração e limite de tokens | Aceito |
| [0027](0027-controle-de-raciocinio.md) | Controle de raciocínio dos modelos gratuitos | Aceito |
| [0028](0028-politica-de-cache.md) | Política de cache: ponteiro para a execução, acerto gravado e campos da chave | Aceito |
| [0029](0029-historico-por-varredura.md) | Histórico por varredura preguiçosa dos arquivos de execução | Aceito |
| [0030](0030-aposentado.md) | Número aposentado (decisão descontinuada removida do projeto) | Aposentado |
| [0031](0031-arquivo-de-comparacao-e-vencedor.md) | Arquivo de comparação, vencedor e empate | Aceito |
| [0032](0032-modelo-do-experimento.md) | Modelo e parâmetros do experimento de comparação | Aceito |
| [0033](0033-limite-de-taxa-por-ip.md) | Limite de taxa por IP em janela deslizante, em memória | Aceito |
| [0034](0034-contrato-do-deploy-conf.md) | Contrato do deploy.conf: dados fora das versões, um worker e pacote enxuto | Aceito |
| [0035](0035-cache-grava-sempre.md) | Cache: gravar sempre e ler só quando pedido | Aceito |
| [0036](0036-confirmar-substituicao-do-cache.md) | Confirmação antes de substituir entradas do cache | Aceito |
| [0037](0037-crud-do-catalogo.md) | CRUD de clientes e tickets direto nos arquivos de `catalog/` | Aceito |
| [0038](0038-cache-das-comparacoes.md) | Cache das comparações e aba Comparar por execuções | Aceito |
| [0039](0039-versao-padrao-e-a-mais-nova.md) | A versão padrão do prompt é sempre a mais nova | Aceito |
| [0040](0040-paridade-funcional-api-site-cli.md) | Paridade funcional entre site, API e CLI | Aceito |
| [0041](0041-cli-adaptador-direto-do-nucleo.md) | CLI como adaptador de entrada direto do núcleo | Aceito |
| [0042](0042-corte-por-limite-decidido-no-servico.md) | Resposta cortada decidida no serviço, com gasto e provedor registrados | Aceito |
| [0043](0043-log-de-eventos-json-lines.md) | Log de eventos em JSON Lines na raiz do projeto | Aceito |

## Template

```markdown
# ADR NNNN · Título curto da decisão

- **Status**: Proposto | Aceito | Aposentado
- **Data**: AAAA-MM-DD

## Contexto
Problema, restrições e forças em jogo.

## Opções consideradas
### Opção A
- **Prós**: ...
- **Contras**: ...
- **Custo**: ...
- **Risco**: ...
(repetir para cada opção, incluindo a escolhida)

## Decisão
O que foi decidido, de forma direta.

## Por que vence
- **O que ganha e o que perde**: ...
- **Por que compensa**: ...

## Consequências
Efeitos no código, nos testes e nas decisões futuras.

## Como verificar
Comando, teste ou inspeção que prova que a decisão está valendo.
```

## Regras de conteúdo

- Apenas argumentos técnicos: sem preferências pessoais, nomes de pessoas nem referências a outros projetos.
- Toda opção tem prós, contras, custo e risco, inclusive a vencedora.
- Novas decisões usam o próximo número livre.
