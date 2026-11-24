"""Testes da comparação (ADR 0021, 0031 e 0040): execuções já geradas, justiça por código, vencedor e arquivo salvo."""

import json
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime

import pytest
from pydantic import BaseModel

from app.adapters.llm.fake import FakeLLM
from app.config import Settings
from app.container import Container, build_container
from app.domain import rubric
from app.domain.comparison import (
    COMPARISON_ID_PATTERN,
    FAIRNESS_FIELDS,
    ComparisonRecord,
    auto_conclusion,
    covers_runs,
    decide_winner,
    find_unfairness,
)
from app.domain.errors import NotFound, ValidationFailed
from app.domain.models import ContentType
from app.ports.llm import ChatMessage, LLMParams, LLMResult
from app.services.comparison import (
    MAX_COMPARISONS_LIMIT,
    find_saved_comparison,
    get_comparison,
    list_comparisons,
    load_comparable_runs,
    save_comparison,
)
from app.services.generators import generate
from tests.support import gerar_versoes

TIPO = ContentType.RESOLUTION_STEPS


def notas(base: int = 4, **mudancas: int) -> dict:
    """Notas válidas; ``notas(3, clarity=5)`` dá 3 em tudo e 5 em clareza."""
    return {
        key: {"score": mudancas.get(key, base), "justification": f"Motivo de {key}."} for key in rubric.CRITERIA_KEYS
    }


@pytest.fixture
def container(settings: Settings) -> Container:
    return build_container(settings)


# --- execuções comparáveis e justiça -----------------------------------------------------------------------


def test_le_as_execucoes_geradas_antes_na_ordem_pedida(container: Container) -> None:
    id1, id2 = gerar_versoes(container)
    lidas = load_comparable_runs(container.runs, [id2, id1])
    assert [s.record.prompt_version for s in lidas] == ["v2", "v1"]
    v1, v2 = lidas[1].record, lidas[0].record
    assert (v1.customer_profile, v1.ticket, v1.content_type) == (v2.customer_profile, v2.ticket, v2.content_type)


@pytest.mark.parametrize(
    ("quais", "trecho"),
    [("uma", "ao menos 2"), ("nenhuma", "ao menos 2"), ("repetidas", "diferentes entre si")],
)
def test_recusa_menos_de_duas_execucoes_ou_repetidas(container: Container, quais: str, trecho: str) -> None:
    id1, _ = gerar_versoes(container)
    ids = {"uma": [id1], "nenhuma": [], "repetidas": [id1, id1]}[quais]
    with pytest.raises(ValidationFailed, match=trecho):
        load_comparable_runs(container.runs, ids)


def test_recusa_execucao_que_veio_do_cache(container: Container) -> None:
    """Um acerto de cache repete a saída da origem: compara-se a origem (a aba Comparar nem o lista)."""
    id1, _ = gerar_versoes(container)
    _, cache_v2 = gerar_versoes(container)  # mesma entrada: a v2 agora vem do cache
    with pytest.raises(ValidationFailed, match=rf"{cache_v2} veio do cache"):
        load_comparable_runs(container.runs, [id1, cache_v2])


def test_recusa_quando_o_modelo_efetivo_difere(settings: Settings) -> None:
    """Mesmo modelo pedido, mas respondido por modelos diferentes: a comparação é injusta (ADR 0021)."""

    class ModelosDiferentes:
        def __init__(self) -> None:
            self._fake = FakeLLM()
            self._chamadas = 0

        def complete(self, messages: Sequence[ChatMessage], schema: type[BaseModel], params: LLMParams) -> LLMResult:
            self._chamadas += 1
            result = self._fake.complete(messages, schema, params)
            efetivo = "vendor/a" if self._chamadas == 1 else "vendor/b"
            return replace(result, model_used=efetivo)

    container = build_container(settings, llm=ModelosDiferentes())
    ids = gerar_versoes(container)
    with pytest.raises(ValidationFailed) as exc:
        load_comparable_runs(container.runs, ids)
    mensagem = str(exc.value)
    assert "Comparação injusta" in mensagem and "modelo efetivo (v1: vendor/a, v2: vendor/b)" in mensagem
    assert "modelo configurado" not in mensagem and "temperatura" not in mensagem  # só o que difere


# Cada campo que a justiça exige igual: o valor alternativo para a execução B.
_DIFERENCAS = {
    "perfil do cliente": {"customer_profile": {
        "id": "marta", "name": "Dona Marta", "tech_level": "avançado", "comm_style": "didático",
        "channel": "telefone",
    }},
    "ticket": {"ticket": {"id": "t-2fa", "title": "SMS", "text": "Outro relato"}},
    "tipo de conteúdo": {"content_type": "flow_summary"},
    "provedor": {"provider": "openrouter"},
    "modelo configurado": {"model": "vendor/outro:free"},
    "modelo efetivo": {"model_used": "vendor/outro"},
    "temperatura": {"params": {"temperature": 0.9, "max_tokens": 1500, "structured_mode": "json_schema"}},
    "max_tokens": {"params": {"temperature": 0.2, "max_tokens": 99, "structured_mode": "json_schema"}},
    "modo estruturado": {"params": {"temperature": 0.2, "max_tokens": 1500, "structured_mode": "prompt"}},
    "raciocínio": {"params": {"temperature": 0.2, "max_tokens": 1500, "structured_mode": "json_schema",
                              "reasoning": "off"}},
}


def test_toda_diferenca_exigida_pelo_adr_0021_esta_coberta() -> None:
    assert {label for label, _, _ in FAIRNESS_FIELDS} == set(_DIFERENCAS)


@pytest.mark.parametrize("campo", list(_DIFERENCAS))
def test_cada_campo_divergente_causa_recusa(make_record, campo: str) -> None:
    a = make_record(prompt_version="v1", model_used="vendor/modelo")
    b = make_record(**{"run_id": "bbbbbbbbbbbb", "prompt_version": "v2", "model_used": "vendor/modelo",
                       **_DIFERENCAS[campo]})
    problemas = find_unfairness([a, b])
    assert len(problemas) == 1 and problemas[0].startswith(campo) and "v1:" in problemas[0] and "v2:" in problemas[0]


def test_cenario_equivalente_e_aceito_e_so_a_versao_pode_diferir(make_record) -> None:
    a = make_record(prompt_version="v1", model_used="vendor/modelo")
    b = make_record(run_id="bbbbbbbbbbbb", prompt_version="v2", model_used="vendor/modelo", prompt_sha256="f" * 64,
                    ticket={"id": "t-2fa", "title": "SMS não chega", "text": "  Texto   do\nticket "})
    assert find_unfairness([a, b]) == []  # espaços diferentes no ticket não contam como outro ticket


def test_varios_campos_divergentes_aparecem_juntos(make_record) -> None:
    a = make_record(prompt_version="v1")
    b = make_record(run_id="bbbbbbbbbbbb", prompt_version="v2", provider="openrouter", model="x")
    assert [p.split(" (")[0] for p in find_unfairness([a, b])] == ["provedor", "modelo configurado"]


def test_salvar_recusa_execucoes_de_configuracoes_diferentes(container: Container) -> None:
    from tests.support import seed_prompt_versions

    seed_prompt_versions(container.settings.prompts_dir, "v2")
    quente = replace(container.generation, config=replace(container.generation.config, temperature=0.9))
    a = generate(container.generation, content_type=TIPO, profile_id="marta", ticket_id="t-2fa", prompt_version="v1")
    b = generate(quente, content_type=TIPO, profile_id="marta", ticket_id="t-2fa", prompt_version="v2")
    ids = [a.record.run_id, b.record.run_id]
    padrao = container.settings.llm_temperature
    with pytest.raises(ValidationFailed, match=rf"temperatura \(v1: {padrao}, v2: 0.9\)"):
        save_comparison(container.comparison, run_ids=ids, evaluations={i: notas() for i in ids})


# --- vencedor ----------------------------------------------------------------------------------------------


def test_vencedor_e_o_maior_total_e_empate_no_topo_nao_tem_vencedor() -> None:
    assert decide_winner({"v1": 9, "v2": 12}) == "v2"
    assert decide_winner({"v1": 12, "v2": 9}) == "v1"
    assert decide_winner({"v1": 10, "v2": 10}) is None
    assert decide_winner({"v1": 8, "v2": 11, "v3": 11}) is None  # empate entre os primeiros de 3
    assert decide_winner({"v1": 8, "v2": 11, "v3": 9}) == "v2"
    assert "venceu" in auto_conclusion({"v1": 9, "v2": 12}, "v2") and "Empate" in auto_conclusion({"v1": 9}, None)


# --- salvar a comparação -----------------------------------------------------------------------------------


def preparar(container: Container, nova: bool = False):
    """Gera a v1 e a v2 (``nova`` força execuções novas, sem acerto de cache) e devolve os registros e os ids."""
    ids = gerar_versoes(container, nova=nova)
    return [container.runs.get(i) for i in ids], ids


def test_salva_comparacao_com_cenario_execucoes_avaliacoes_total_vencedor_e_conclusao(
    container: Container, settings: Settings
) -> None:
    # Salva a comparação e confere arquivo gravado, totais, vencedor e reflexão no histórico.
    resultados, (id1, id2) = preparar(container)
    stored = save_comparison(
        container.comparison,
        run_ids=[id1, id2],
        evaluations={id1: notas(3), id2: notas(4, clarity=5)},
        conclusion="  A v2 adaptou melhor ao perfil.  ",
    )
    record = stored.record
    # Arquivo em var/comparisons/<id>.json e relido sem perdas.
    caminho = settings.data_dir / "comparisons" / f"{record.comparison_id}.json"
    assert stored.saved_path == str(caminho) and caminho.is_file()
    assert ComparisonRecord.model_validate_json(caminho.read_text(encoding="utf-8")) == record
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    assert {"scenario", "versions", "winner", "conclusion", "created_at"} <= set(bruto)
    # Cenário, ids das execuções, avaliações por versão e total por versão.
    assert record.scenario.customer_id == "marta" and record.scenario.ticket.id == "t-2fa"
    assert record.scenario.content_type is TIPO and record.scenario.model_used == "fake-llm"
    assert [(v.prompt_version, v.run_id) for v in record.versions] == [("v1", id1), ("v2", id2)]
    v1, v2 = record.versions
    assert (v1.total, v2.total) == (9, 13)
    assert v1.evaluation["clarity"] == {"score": 3, "justification": "Motivo de clarity."}
    assert v2.evaluation["evaluator"] == "candidato" and v2.output == resultados[1].record.output
    assert record.winner == "v2" and record.conclusion == "A v2 adaptou melhor ao perfil."
    assert record.conclusion_source == "candidato"
    # As notas também foram gravadas nas execuções (o histórico as mostra).
    assert container.runs.get(id2).record.evaluation == v2.evaluation


def test_empate_e_conclusao_automatica(container: Container) -> None:
    _, (id1, id2) = preparar(container)
    record = save_comparison(
        container.comparison, run_ids=[id1, id2], evaluations={id1: notas(4), id2: notas(4)}
    ).record
    assert record.winner is None and "Empate" in record.conclusion and record.conclusion_source == "automática"


def test_cada_comparacao_e_avaliada_do_zero_mesmo_com_nota_gravada(container: Container) -> None:
    _, (id1, id2) = preparar(container)
    save_comparison(container.comparison, run_ids=[id1, id2], evaluations={id1: notas(5), id2: notas(1)})
    with pytest.raises(ValidationFailed, match=rf"{id2} \(v2\) não tem avaliação"):
        save_comparison(container.comparison, run_ids=[id1, id2], evaluations={id1: notas(5)})


def test_exige_avaliacao_completa_de_cada_lado_e_nao_grava_nada_se_faltar(
    container: Container, settings: Settings
) -> None:
    _, (id1, id2) = preparar(container)
    with pytest.raises(ValidationFailed, match=rf"{id2} \(v2\) não tem avaliação"):
        save_comparison(container.comparison, run_ids=[id1, id2], evaluations={id1: notas()})
    assert container.runs.get(id1).record.evaluation is None  # a nota válida do outro lado não foi gravada
    assert not (settings.data_dir / "comparisons").exists()


def test_nota_invalida_em_um_lado_nao_grava_nenhum(container: Container, settings: Settings) -> None:
    _, (id1, id2) = preparar(container)
    ruim = notas()
    ruim["actionability"]["score"] = 7
    with pytest.raises(ValidationFailed, match="Acionabilidade: a nota deve ser um inteiro de 1 a 5"):
        save_comparison(container.comparison, run_ids=[id1, id2], evaluations={id1: notas(), id2: ruim})
    assert container.runs.get(id1).record.evaluation is None
    assert not (settings.data_dir / "comparisons").exists()


@pytest.mark.parametrize("quais", ["uma", "repetidas", "estranha", "mesma_versao", "longa", "erro"])
def test_recusas_do_salvamento(container: Container, make_record, quais: str) -> None:
    _, (id1, id2) = preparar(container)
    ids, avaliacoes, conclusao = [id1, id2], {id1: notas(), id2: notas()}, None
    if quais == "uma":
        ids = [id1]
    elif quais == "repetidas":
        ids = [id1, id1]
    elif quais == "estranha":
        avaliacoes["ffffffffffff"] = notas()
    elif quais == "longa":
        conclusao = "x" * 1001
    elif quais == "mesma_versao":
        outra = generate(container.generation, content_type=TIPO, profile_id="marta", ticket_id="t-2fa",
                         prompt_version="v1")
        ids, avaliacoes = [id1, outra.record.run_id], {id1: notas(), outra.record.run_id: notas()}
    elif quais == "erro":
        container.runs.save(make_record(run_id="eeeeeeeeeeee", status="error", error={"type": "X", "message": "m"}))
        ids, avaliacoes = [id1, "eeeeeeeeeeee"], {id1: notas(), "eeeeeeeeeeee": notas()}
    with pytest.raises(ValidationFailed):
        save_comparison(container.comparison, run_ids=ids, evaluations=avaliacoes, conclusion=conclusao)


def test_execucao_inexistente_no_salvamento_e_not_found(container: Container) -> None:
    _, (id1, _) = preparar(container)
    with pytest.raises(NotFound):
        save_comparison(container.comparison, run_ids=[id1, "ffffffffffff"], evaluations={})


def test_erro_ao_salvar_comparacao_nao_grava_notas_nas_execucoes(container: Container) -> None:
    from unittest.mock import patch

    _, (id1, id2) = preparar(container)
    with patch.object(container.comparisons, "save", side_effect=OSError("disk full")):
        with pytest.raises(OSError, match="disk full"):
            save_comparison(container.comparison, run_ids=[id1, id2], evaluations={id1: notas(), id2: notas()})
    assert container.runs.get(id1).record.evaluation is None
    assert container.runs.get(id2).record.evaluation is None


# --- listar e abrir -----------------------------------------------------------------------------------------


def test_lista_da_mais_recente_para_a_mais_antiga_e_abre_por_id(container: Container, settings: Settings) -> None:
    ids = []
    relogio = iter(range(10, 20))
    comparacao = replace(
        container.comparison,
        clock=lambda tz: datetime(2026, 11, 20, 12, next(relogio), 0, tzinfo=tz),
    )
    for _ in range(3):
        _, (a, b) = preparar(container, nova=True)
        salva = save_comparison(comparacao, run_ids=[a, b], evaluations={a: notas(), b: notas(5)})
        ids.append(salva.record.comparison_id)
    listadas = list_comparisons(container.comparisons)
    assert [s.record.comparison_id for s in listadas.items] == list(reversed(ids)) and listadas.total == 3
    pagina = list_comparisons(container.comparisons, 2)
    assert [s.record.comparison_id for s in pagina.items] == list(reversed(ids))[:2] and pagina.pages == 2
    segunda = list_comparisons(container.comparisons, 2, 2)
    assert [s.record.comparison_id for s in segunda.items] == [ids[0]] and segunda.page == 2
    aberta = get_comparison(container.comparisons, ids[0])
    assert aberta.record.comparison_id == ids[0] and aberta.saved_path.endswith(f"{ids[0]}.json")


def test_listagem_pula_arquivo_ilegivel_e_valida_limite_e_id(container: Container, settings: Settings) -> None:
    assert list_comparisons(container.comparisons).items == []  # sem pasta ainda
    _, (a, b) = preparar(container)
    salvo = save_comparison(container.comparison, run_ids=[a, b], evaluations={a: notas(), b: notas()})
    (settings.data_dir / "comparisons" / "aaaaaaaaaaaa.json").write_text("{quebrado", encoding="utf-8")
    assert [s.record.comparison_id for s in list_comparisons(container.comparisons).items] == [
        salvo.record.comparison_id
    ]
    for ruim in (0, MAX_COMPARISONS_LIMIT + 1):
        with pytest.raises(ValidationFailed):
            list_comparisons(container.comparisons, ruim)
    with pytest.raises(ValidationFailed, match="negativo"):
        list_comparisons(container.comparisons, 10, -1)
    for id_ruim in ("aaaaaaaaaaaa", "../x", "*", "ZZZZZZZZZZZZ", "abc"):
        with pytest.raises(NotFound):
            get_comparison(container.comparisons, id_ruim)
    assert COMPARISON_ID_PATTERN and len(salvo.record.comparison_id) == 12


def test_versoes_ficam_em_ordem_numerica_independente_da_ordem_dos_ids(container: Container) -> None:
    _, (id1, id2) = preparar(container)
    record = save_comparison(
        container.comparison, run_ids=[id2, id1], evaluations={id1: notas(), id2: notas()}
    ).record
    assert [v.prompt_version for v in record.versions] == ["v1", "v2"]


# --- cache das comparações (ADR 0038) ----------------------------------------------------------------------


def test_cache_da_comparacao_acha_o_mesmo_conjunto_de_execucoes_em_qualquer_ordem(container: Container) -> None:
    _, (a, b) = preparar(container)
    assert find_saved_comparison(container.comparisons, [a, b]) is None
    salva = save_comparison(container.comparison, run_ids=[a, b], evaluations={a: notas(), b: notas(5)})
    for ordem in ([a, b], [b, a]):
        achada = find_saved_comparison(container.comparisons, ordem)
        assert achada is not None and achada.record.comparison_id == salva.record.comparison_id
        assert covers_runs(achada.record, ordem)


def test_cache_da_comparacao_nao_confunde_conjuntos_diferentes(container: Container) -> None:
    a, b, c = gerar_versoes(container, ("v1", "v2", "v3"))
    salva = save_comparison(container.comparison, run_ids=[a, b], evaluations={a: notas(), b: notas(5)})
    assert find_saved_comparison(container.comparisons, [a, c]) is None
    assert find_saved_comparison(container.comparisons, [a, b, c]) is None  # o conjunto maior não é o salvo
    assert not covers_runs(salva.record, [a])


def test_cache_da_comparacao_devolve_a_mais_recente_e_valida_a_entrada(container: Container) -> None:
    relogio = iter(range(10, 20))
    comparacao = replace(
        container.comparison, clock=lambda tz: datetime(2026, 11, 20, 12, next(relogio), 0, tzinfo=tz)
    )
    _, (a, b) = preparar(container)
    save_comparison(comparacao, run_ids=[a, b], evaluations={a: notas(), b: notas(5)})
    nova = save_comparison(comparacao, run_ids=[a, b], evaluations={a: notas(2), b: notas(3)})  # outra, do zero
    achada = find_saved_comparison(container.comparisons, [a, b])
    assert achada is not None and achada.record.comparison_id == nova.record.comparison_id
    with pytest.raises(ValidationFailed, match="ao menos 2"):
        find_saved_comparison(container.comparisons, [a])
    with pytest.raises(ValidationFailed, match="diferentes entre si"):
        find_saved_comparison(container.comparisons, [a, a])
