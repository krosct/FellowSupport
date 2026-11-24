# ADR 0032 · Modelo e parâmetros do experimento de comparação

- **Status**: Aceito (complementa os ADRs 0021, 0026 e 0027)
- **Data**: 2026-11-20

## Contexto

O experimento de comparação entre versões de prompt em vários cenários exige orçamento controlado de chamadas reais. O ADR 0021 exige que a comparação use o mesmo
modelo e os mesmos parâmetros nas versões; o ADR 0026 mediu o modelo padrão (`baidu/ernie-5.5-flash-preview:free`) e
o ADR 0027 mediu que ele tem raciocínio obrigatório: 20 a 40 s por geração, até 8000 tokens de saída e cortes por
`max_tokens` (passo a passo com 8000 tokens e diagnóstico do ticket complexo cortados, sem JSON). O `nvidia/nemotron-3.5-super-vl:free`
aceita `LLM_REASONING=off` (ADR 0027, chamada 3).

Medição com `nvidia/nemotron-3.5-super-vl:free`, `LLM_REASONING=off`, `LLM_MAX_TOKENS=4000`,
`LLM_MAX_RETRIES=0` e temperatura 0,1: 11 gerações reais (seis passos a passo, três diagnósticos, um conjunto de
perguntas e um fluxo), todas válidas na primeira tentativa (`attempts: 1`), sem reparo e sem corte. Latência de
4,0 s a 18,3 s (mediana 5,4 s); 313 a 1420 tokens de saída, sem tokens de raciocínio.

## Opções consideradas

### Nemotron com `LLM_REASONING=off`, 4000 tokens e sem retentativas do SDK, só no experimento (por variável de ambiente)

- **Prós**: Medido: 11 de 11 gerações válidas de primeira, 5,4 s de mediana, menos de 1,5 mil tokens por geração;
  `MAX_RETRIES=0` faz o número de chamadas ser igual a `attempts` e deixa a contagem do orçamento exata.
- **Contras**: O padrão do projeto é outro modelo, então o resultado vale para este modelo com raciocínio desligado e
  pode não valer para o padrão.
- **Custo**: Zero em dinheiro; 11 gerações reais com baixo consumo de cota.
- **Risco**: Médio: a conclusão sobre o prompt depende do modelo; mitigado por registrar o modelo e os parâmetros em
  cada execução e por recusar comparações com modelos diferentes (ADR 0021).

### Manter o modelo padrão (`baidu/ernie-5.5-flash-preview:free`, 8000 tokens)

- **Prós**: É o padrão documentado, então o experimento reproduz o uso comum do projeto.
- **Contras**: Medido no ADR 0026 e no ADR 0027: de 20 a 40 s por geração e cortes por limite de tokens em dois de
  quatro tipos de conteúdo; cada comparação de 3 versões levaria minutos, e um corte sem JSON gasta uma chamada
  do orçamento sem produzir amostra.
- **Custo**: Alto em latência e em cota de tokens gratuitos.
- **Risco**: Alto: cortes tornam a amostra incompleta e enviesam a comparação para os cenários simples.

### Trocar o padrão do projeto para o nemotron com `off`

- **Prós**: O experimento e o uso diário passariam a usar a mesma configuração.
- **Contras**: A evidência é de 11 gerações em três cenários e três perfis, sem repetição para medir variância e com
  um só provedor; o ADR 0027 já exigiu medições maiores antes de trocar o padrão, e o ADR 0026 continua valendo.
- **Custo**: Baixo em código, mas invalida o cache e os documentos que citam o padrão atual.
- **Risco**: Médio: generalizar uma amostra pequena.

### Nemotron com raciocínio ligado (`LLM_REASONING=default`)

- **Prós**: Mais próximo do uso do modelo de raciocínio sem ajuste.
- **Contras**: No ADR 0026 (chamada 5) o mesmo modelo gastou 6826 tokens de raciocínio e foi cortado em 8000 no
  ticket complexo.
- **Custo**: Alto em tokens e latência.
- **Risco**: Alto: cortes sem JSON.

## Decisão

O experimento de comparação usa `nvidia/nemotron-3.5-super-vl:free` com `LLM_REASONING=off`, `LLM_MAX_TOKENS=4000` e
`LLM_MAX_RETRIES=0`, passados por variável de ambiente nos comandos que chamam o modelo. O modelo padrão do projeto não muda.

## Por que vence

- **O que ganha e o que perde**: Ganha amostras completas, rápidas e comparáveis dentro do orçamento. Perde a
  representatividade do modelo padrão.
- **Por que compensa**: A pergunta do experimento é relativa (qual versão do prompt serve melhor no mesmo modelo), e
  só uma configuração que entrega JSON de primeira a responde sem lacunas; as limitações ficam registradas nas notas.

## Consequências

- Todas as execuções em `var/runs/` carregam `model_used` e `params`; a CLI e o cache seguem os valores recebidos.
- Os resultados não se estendem ao modelo padrão sem repetir o experimento com ele (ponto de medição futuro).
- Mudar o modelo, o raciocínio ou o limite de tokens muda a chave de cache (ADR 0028).

## Como verificar

`.venv/bin/python -m app.adapters.cli.main history generation --version v3` lista as execuções dessa versão e
`.venv/bin/python -m app.adapters.cli.main show <run_id> --json` exibe `model_used` e `params`. Os testes usam o
provedor `fake` e não chamam a rede.
