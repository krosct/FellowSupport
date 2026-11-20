# ADR 0002 · Arquitetura hexagonal (Ports and Adapters)

- **Status**: Aceito
- **Data**: 2026-11-20

## Contexto

O sistema depende de elementos instáveis ou caros: um LLM remoto, armazenamento em arquivos e duas interfaces de entrada (web e CLI). É preciso testar sem rede nem custo e trocar provedor ou armazenamento sem reescrever regras.

## Opções consideradas

### Hexagonal: domain, ports, services, adapters e container

- **Prós**: Domínio testável sem I/O; troca de LLM e de armazenamento sem tocar nas regras; permite um LLM falso nos testes.
- **Contras**: Mais arquivos e indireção para um projeto pequeno.
- **Custo**: Baixo a médio: disciplina para manter as dependências apontando para dentro.
- **Risco**: Baixo: superengenharia se as portas crescerem sem necessidade.

### Script único

- **Prós**: Rápido de escrever e fácil de ler no começo.
- **Contras**: Mistura prompt, HTTP, I/O e regras; impossível testar sem rede; difícil comparar versões de forma isolada.
- **Custo**: Baixo no início, alto na manutenção.
- **Risco**: Alto: a nota de implementação e a testabilidade ficam comprometidas.

### MVC em camadas (controller, service, repository)

- **Prós**: Padrão conhecido, estrutura previsível.
- **Contras**: Tende a acoplar o serviço ao framework web e ao SDK do LLM; o domínio acaba importando infraestrutura.
- **Custo**: Médio.
- **Risco**: Médio: trocar o provedor de LLM exige mudanças em várias camadas.

## Decisão

Arquitetura hexagonal com `domain/` (modelos, regras, rubrica, erros), `ports/` (Protocols), `services/` (casos de uso), `adapters/` (API, CLI, LLM, armazenamento) e `container.py` como raiz de composição.

## Por que vence

- **O que ganha e o que perde**: Ganha testabilidade, troca de provedor por configuração e domínio sem dependências externas. Perde alguns arquivos a mais e uma camada de indireção.
- **Por que compensa**: Compensa porque o ponto central do desafio é comparar prompts de forma reproduzível, o que exige executar o pipeline inteiro sem rede.

## Consequências

O domínio não importa FastAPI, `openai` nem faz I/O. Cada nova capacidade externa entra como porta mais adaptador.

## Como verificar

Teste ou verificação estática de que `app/domain` não importa `fastapi`, `openai` nem `httpx`; testes do núcleo rodando com adaptadores falsos.
