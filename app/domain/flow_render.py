"""Desenha o ``FlowSummary`` como fluxograma ASCII (ADR 0008).

Função pura e determinística: a mesma estrutura gera sempre exatamente o mesmo texto, sem relógio, sem
aleatoriedade e sem ler nada de fora. Por isso o desenho é testável por snapshot, ao contrário de pedir o ASCII
ao modelo (que desalinha). O desenho é uma árvore descendo pela tela:

- ``(INÍCIO)`` abre o fluxo; ações são ``[n]``, decisões ``<n>`` e finais ``[n] FIM:``, numerados na ordem em
  que aparecem;
- passos em sequência ficam na mesma coluna, ligados por ``│`` e ``▼``;
- cada ramo de uma decisão sai em ``├─ Sim ─▶`` (ou ``└─ Não ─▶`` no último) e abre uma coluna recuada;
- quando dois caminhos chegam ao mesmo nó (convergência), ele é desenhado uma vez e o outro caminho aponta
  para ele com ``(segue em [n])``. Se o alvo é um ancestral (ciclo, que o schema já rejeita), o texto é
  ``(volta a [n])``: a proteção evita laço infinito mesmo com um grafo montado sem validação.
"""

from __future__ import annotations

import textwrap

from app.domain.models import FlowEdge, FlowNode, FlowNodeType, FlowSummary

# Largura máxima do texto de um nó; rótulos maiores quebram em linhas alinhadas sob o início do texto.
LABEL_WIDTH = 48

# Rótulos dos ramos que sempre vêm primeiro e por último, para o "Sim" ficar acima do "Não" (comparação sem
# acento nem caixa). Outros rótulos ficam no meio, na ordem original.
_FIRST_BRANCH = {"sim"}
_LAST_BRANCH = {"não", "nao"}

_START_MARKER = "(INÍCIO) "


def _branch_rank(edge: FlowEdge) -> int:
    """Posição do ramo: Sim (0), demais (1), Não (2). A ordenação é estável, preservando a ordem de entrada."""
    label = edge.label.strip().casefold()
    if label in _FIRST_BRANCH:
        return 0
    return 2 if label in _LAST_BRANCH else 1


class _Renderer:
    """Estado de um desenho: nós visitados, numeração e linhas produzidas."""

    def __init__(self, flow: FlowSummary) -> None:
        self._nodes: dict[str, FlowNode] = {node.id: node for node in flow.nodes}
        self._out: dict[str, list[FlowEdge]] = {node.id: [] for node in flow.nodes}
        for edge in flow.edges:
            self._out[edge.source].append(edge)
        self._numbers: dict[str, int] = {}  # id -> número exibido (o start não é numerado)
        self._visited: set[str] = set()
        self._lines: list[str] = []

    def render(self, start_id: str) -> str:
        """Desenha a partir do nó inicial e devolve o texto, sem espaços no fim das linhas."""
        self._emit(start_id, "", "", ())
        return "\n".join(line.rstrip() for line in self._lines)

    def _tag(self, node: FlowNode) -> str:
        """Identificador curto do nó, usado nos marcadores e nas referências (``[3]``, ``<2>``, ``INÍCIO``)."""
        if node.type is FlowNodeType.START:
            return "INÍCIO"
        number = self._numbers[node.id]
        return f"<{number}>" if node.type is FlowNodeType.DECISION else f"[{number}]"

    def _marker(self, node: FlowNode) -> str:
        """Texto que precede o rótulo do nó na primeira linha."""
        if node.type is FlowNodeType.START:
            return _START_MARKER
        if node.type is FlowNodeType.END:
            return f"{self._tag(node)} FIM: "
        return f"{self._tag(node)} "

    def _emit(self, node_id: str, first: str, rest: str, path: tuple[str, ...]) -> None:
        """Desenha o nó e, recursivamente, o que vem depois.

        ``first`` é o prefixo da primeira linha do nó (já com o conector do ramo) e ``rest`` o das linhas
        seguintes e de tudo que desce dele. ``path`` são os ancestrais do caminho atual (detecta ciclo).
        """
        node = self._nodes[node_id]
        if node_id in self._visited:
            # Já desenhado: convergência (outro caminho) ou ciclo (ancestral). Só aponta para ele.
            verb = "volta a" if node_id in path else "segue em"
            self._lines.append(f"{first}({verb} {self._tag(node)})")
            return
        self._visited.add(node_id)
        if node.type is not FlowNodeType.START:
            self._numbers[node_id] = len(self._numbers) + 1

        marker = self._marker(node)
        wrapped = textwrap.wrap(node.label, width=LABEL_WIDTH) or [node.label]
        self._lines.append(f"{first}{marker}{wrapped[0]}")
        # Linhas de continuação do rótulo alinham sob o início do texto, não sob o marcador.
        self._lines.extend(f"{rest}{' ' * len(marker)}{text}" for text in wrapped[1:])

        outgoing = self._out[node_id]
        if node.type is FlowNodeType.END or not outgoing:
            return
        here = (*path, node_id)
        if node.type is FlowNodeType.DECISION:
            branches = sorted(outgoing, key=_branch_rank)
            for index, edge in enumerate(branches):
                is_last = index == len(branches) - 1
                head = f"{'└─' if is_last else '├─'} {edge.label.strip()} ─▶ "
                # Sob um ramo que não é o último, a guia │ continua na coluna do conector; no último, some.
                child_rest = rest + ("   " if is_last else "│  ") + " " * (len(head) - 3)
                self._emit(edge.target, rest + head, child_rest, here)
        else:
            # Passo em sequência: conector vertical e o próximo nó na mesma coluna.
            self._lines.append(f"{rest}│")
            self._lines.append(f"{rest}▼")
            self._emit(outgoing[0].target, rest, rest, here)


def render_flow(flow: FlowSummary) -> str:
    """Fluxograma ASCII do ``flow``. ``ValueError`` se não houver nó ``start`` (grafo montado sem validação)."""
    starts = [node for node in flow.nodes if node.type is FlowNodeType.START]
    if len(starts) != 1:
        raise ValueError("o fluxo precisa de exatamente um nó start para ser desenhado")
    return _Renderer(flow).render(starts[0].id)
