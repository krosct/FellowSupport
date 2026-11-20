"""Testes do renderizador ASCII: snapshots (linear, ramificação com convergência, rótulo longo), ordem dos
ramos, determinismo e proteção contra ciclos (ADR 0008)."""

from __future__ import annotations

import pytest

from app.domain.flow_render import LABEL_WIDTH, render_flow
from app.domain.models import FlowEdge, FlowNode, FlowSummary


def _fluxo(nos: list[tuple[str, str, str]], arestas: list[tuple[str, str, str]]) -> FlowSummary:
    return FlowSummary(
        nodes=[FlowNode(id=i, type=t, label=rotulo) for i, t, rotulo in nos],
        edges=[FlowEdge(source=a, target=b, label=rotulo) for a, b, rotulo in arestas],
    )


LINEAR = _fluxo(
    [("a", "start", "Cliente não recebe o SMS"), ("b", "action", "Conferir o número"),
     ("c", "action", "Pedir novo código"), ("d", "end", "Resolvido")],
    [("a", "b", ""), ("b", "c", ""), ("c", "d", "")],
)

# Duas decisões aninhadas e convergência: o ramo "Não" da primeira e o "Sim" da segunda terminam no mesmo fim.
RAMIFICADO = _fluxo(
    [("n1", "start", "SMS não chega"), ("n2", "decision", "O número cadastrado está correto?"),
     ("n3", "action", "Corrigir o número no cadastro"), ("n4", "decision", "O sinal do celular está bom?"),
     ("n5", "action", "Aguardar a operadora e pedir novo código"),
     ("n6", "end", "Escalar para o N3 com os logs do envio"), ("n7", "end", "Resolvido")],
    [("n1", "n2", ""), ("n2", "n3", "Não"), ("n2", "n4", "Sim"), ("n3", "n7", ""), ("n4", "n5", "Sim"),
     ("n4", "n6", "Não"), ("n5", "n7", "")],
)

ROTULO_LONGO = _fluxo(
    [("a", "start", "Dashboard lento"),
     ("b", "decision", "O problema começou logo depois da importação do histórico completo de marcações do ano?"),
     ("c", "end", "Reduzir o período"), ("d", "end", "Investigar a rede")],
    [("a", "b", ""), ("b", "c", "Sim"), ("b", "d", "Não")],
)


def test_snapshot_linear() -> None:
    assert render_flow(LINEAR) == "\n".join([
        "(INÍCIO) Cliente não recebe o SMS",
        "│",
        "▼",
        "[1] Conferir o número",
        "│",
        "▼",
        "[2] Pedir novo código",
        "│",
        "▼",
        "[3] FIM: Resolvido",
    ])


def test_snapshot_ramificacao_e_convergencia() -> None:
    assert render_flow(RAMIFICADO) == "\n".join([
        "(INÍCIO) SMS não chega",
        "│",
        "▼",
        "<1> O número cadastrado está correto?",
        "├─ Sim ─▶ <2> O sinal do celular está bom?",
        "│         ├─ Sim ─▶ [3] Aguardar a operadora e pedir novo código",
        "│         │         │",
        "│         │         ▼",
        "│         │         [4] FIM: Resolvido",
        "│         └─ Não ─▶ [5] FIM: Escalar para o N3 com os logs do envio",
        "└─ Não ─▶ [6] Corrigir o número no cadastro",
        "          │",
        "          ▼",
        "          (segue em [4])",
    ])


def test_snapshot_rotulo_longo_quebra_alinhado() -> None:
    assert render_flow(ROTULO_LONGO) == "\n".join([
        "(INÍCIO) Dashboard lento",
        "│",
        "▼",
        "<1> O problema começou logo depois da importação do",
        "    histórico completo de marcações do ano?",
        "├─ Sim ─▶ [2] FIM: Reduzir o período",
        "└─ Não ─▶ [3] FIM: Investigar a rede",
    ])


def test_ramo_sim_vem_antes_do_nao_mesmo_se_a_ordem_das_arestas_for_inversa() -> None:
    invertido = _fluxo(
        [("a", "start", "Início"), ("b", "decision", "Funciona?"), ("c", "end", "Fim A"), ("d", "end", "Fim B")],
        [("a", "b", ""), ("b", "d", "Não"), ("b", "c", "Sim")],
    )
    linhas = render_flow(invertido).splitlines()
    assert linhas[-2].startswith("├─ Sim ─▶") and linhas[-1].startswith("└─ Não ─▶")


def test_rotulos_diferentes_de_sim_e_nao_mantem_a_ordem_e_o_ultimo_fecha() -> None:
    tres = _fluxo(
        [("a", "start", "Início"), ("b", "decision", "Qual canal?"), ("c", "end", "Chat"), ("d", "end", "E-mail"),
         ("e", "end", "Telefone")],
        [("a", "b", ""), ("b", "c", "Chat"), ("b", "d", "E-mail"), ("b", "e", "Telefone")],
    )
    linhas = render_flow(tres).splitlines()[-3:]
    assert [linha[:2] for linha in linhas] == ["├─", "├─", "└─"]


def test_e_deterministico_e_sem_espaco_no_fim_das_linhas() -> None:
    for fluxo in (LINEAR, RAMIFICADO, ROTULO_LONGO):
        primeiro = render_flow(fluxo)
        assert primeiro == render_flow(fluxo.model_copy(deep=True))
        assert all(linha == linha.rstrip() for linha in primeiro.splitlines())


def test_nenhuma_linha_de_rotulo_passa_da_largura() -> None:
    for linha in render_flow(ROTULO_LONGO).splitlines():
        if linha.startswith("<1>") or linha.startswith("    "):
            assert len(linha) <= len("<1> ") + LABEL_WIDTH


def test_protecao_contra_ciclo_nao_entra_em_laco() -> None:
    """Um grafo com ciclo só existe se montado sem validação; o renderizador termina e aponta a volta."""
    nos = [FlowNode(id="a", type="start", label="Início"), FlowNode(id="b", type="action", label="Tentar"),
           FlowNode(id="c", type="decision", label="Deu certo?"), FlowNode(id="d", type="end", label="Fim")]
    arestas = [FlowEdge(source="a", target="b", label=""), FlowEdge(source="b", target="c", label=""),
               FlowEdge(source="c", target="b", label="Não"), FlowEdge(source="c", target="d", label="Sim")]
    ciclico = FlowSummary.model_construct(nodes=nos, edges=arestas)
    assert render_flow(ciclico) == "\n".join([
        "(INÍCIO) Início",
        "│",
        "▼",
        "[1] Tentar",
        "│",
        "▼",
        "<2> Deu certo?",
        "├─ Sim ─▶ [3] FIM: Fim",
        "└─ Não ─▶ (volta a [1])",
    ])


def test_fluxo_sem_start_levanta_erro() -> None:
    sem_inicio = FlowSummary.model_construct(nodes=[FlowNode(id="a", type="end", label="Fim")], edges=[])
    with pytest.raises(ValueError, match="start"):
        render_flow(sem_inicio)
