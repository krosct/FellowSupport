# ADR 0014 · Constantes do domínio servidas por GET /api/meta

- **Status**: Aceito
- **Data**: 2026-11-20

## Contexto

Enums do perfil, tipos de conteúdo, rubrica e versão padrão são necessários no back e no front. Duplicar essas listas no JavaScript as faria divergir.

## Opções consideradas

### Endpoint `GET /api/meta` com enums, tipos de conteúdo, rubrica e versão padrão; o front só consome

- **Prós**: Fonte única de verdade (SSOT); mudar a rubrica ou um enum em um lugar atualiza o front.
- **Contras**: O front depende de uma chamada inicial; sem a API, não há rótulos.
- **Custo**: Baixo.
- **Risco**: Baixo: o front mostra erro por toast se a chamada falhar.

### Constantes duplicadas no JavaScript

- **Prós**: Front independente da API para renderizar rótulos.
- **Contras**: Divergência com o tempo; viola a regra de definição única.
- **Custo**: Baixo no início.
- **Risco**: Alto: inconsistência silenciosa.

### Gerar um arquivo de constantes em build

- **Prós**: Sem chamada em tempo de execução.
- **Contras**: Passo de build extra; risco de arquivo desatualizado.
- **Custo**: Médio.
- **Risco**: Médio.

## Decisão

`GET /api/meta` é a fonte dos rótulos e valores para o front. O endpoint nunca expõe segredo nem configuração sensível.

## Por que vence

- **O que ganha e o que perde**: Ganha consistência garantida. Perde a independência do front em relação à API.
- **Por que compensa**: Compensa porque o front só funciona com a API de qualquer forma.

## Consequências

O front não define listas de níveis, estilos, canais, tipos nem critérios da rubrica.

## Como verificar

Teste do endpoint (chaves esperadas, ausência de segredo) e busca no front por literais de enums, que deve retornar vazio.
