"""Story points, MoSCoW e RICE (requisitos 14 a 19)."""
from decimal import Decimal

import pytest

from sgr.services.auth_service import ErroDeValidacao
from sgr.services.historia_service import HistoriaNaoEncontrada
from sgr.services.priorizacao_service import PriorizacaoService
from sgr.services.rice import calcular_rice, validar_rice
from tests.fabricas import auditoria, cenario, criar_historia  # noqa: F401


@pytest.fixture()
def prio(cenario):
    return PriorizacaoService(cenario.historias._sessao)


# ---------- cálculo (sem banco) ----------


@pytest.mark.parametrize("entradas,nota", [
    ((1000, 2, 80, 5), "320.00"),       # 1000 × 2 × 0,8 / 5
    ((500, 0.5, 50, 3), "41.67"),       # 125 / 3
    ((0, 3, 100, 1), "0.00"),           # sem alcance, sem nota
    ((100, 0.25, 50, 55), "0.23"),
    ((5, 0.25, 50, 1), "0.63"),         # 0,625: arredonda para cima, não para o par
    ((10000, 3, 100, 1), "30000.00"),
])
def test_calcula_a_formula_com_confidence_em_percentual(entradas, nota):
    assert calcular_rice(*entradas) == Decimal(nota)


@pytest.mark.parametrize("impact", [2, 2.0, "2", Decimal("2"), "0,5", "0.5", 0.5, Decimal("0.50")])
def test_impact_aceita_as_formas_de_escrever_o_mesmo_valor(impact):
    assert validar_rice(10, impact, 100, 1)[1] in (Decimal(2), Decimal("0.5"))


@pytest.mark.parametrize("campo,valor", [
    ("rice_reach", -1), ("rice_reach", 1.5), ("rice_reach", "abc"), ("rice_reach", True),
    ("rice_impact", 4), ("rice_impact", 0), ("rice_impact", 0.3), ("rice_impact", "x"), ("rice_impact", True),
    ("rice_confidence", 90), ("rice_confidence", 0), ("rice_confidence", 1), ("rice_confidence", True),
    ("rice_effort", 0), ("rice_effort", 4), ("rice_effort", 56), ("rice_effort", True),
    ("rice_effort", float("nan")),
])
def test_valor_fora_do_dominio_e_recusado_com_o_campo_certo(campo, valor):
    entradas = {"rice_reach": 10, "rice_impact": 2, "rice_confidence": 80, "rice_effort": 5}
    entradas[campo] = valor
    with pytest.raises(ErroDeValidacao) as erro:
        calcular_rice(*entradas.values())
    assert set(erro.value.erros) == {campo}


def test_effort_zero_explica_a_regra_e_o_formulario_mostra_todos_os_erros_de_uma_vez():
    with pytest.raises(ErroDeValidacao) as erro:
        validar_rice(-5, 7, 33, 0)
    assert set(erro.value.erros) == {"rice_reach", "rice_impact", "rice_confidence", "rice_effort"}
    assert "21" in erro.value.erros["rice_effort"] and "0," not in erro.value.erros["rice_effort"]


def test_as_quatro_entradas_sao_obrigatorias():
    with pytest.raises(ErroDeValidacao) as erro:
        calcular_rice(None, None, None, None)
    assert set(erro.value.erros) == {"rice_reach", "rice_impact", "rice_confidence", "rice_effort"}
    assert all(m.startswith("Informe") for m in erro.value.erros.values())


# ---------- story points ----------


@pytest.mark.parametrize("pontos", [0, 1, 2, 3, 5, 8, 13, 21, 34, 55])
def test_atribui_cada_valor_da_escala(cenario, prio, pontos):
    h = criar_historia(cenario)
    assert prio.definir_story_points(cenario.dono, h.id, pontos).story_points == pontos
    assert cenario.historias.obter(cenario.dono, h.id).story_points == pontos


@pytest.mark.parametrize("pontos", [4, -1, 56, 7, True, "5", 2.5])
def test_story_points_fora_da_escala_nao_alteram_nada(cenario, prio, pontos):
    h = criar_historia(cenario, story_points=3)
    with pytest.raises(ErroDeValidacao) as erro:
        prio.definir_story_points(cenario.dono, h.id, pontos)
    assert set(erro.value.erros) == {"story_points"}
    assert cenario.historias.obter(cenario.dono, h.id).story_points == 3
    assert auditoria(cenario.conn, "historia", "ALTERAR") == []


def test_story_points_none_remove_a_estimativa_e_audita(cenario, prio):
    h = criar_historia(cenario, story_points=8)
    assert prio.definir_story_points(cenario.dono, h.id, None).story_points is None
    (linha,) = auditoria(cenario.conn, "historia", "ALTERAR")
    assert linha.valor_anterior == {"story_points": 8} and linha.valor_posterior == {"story_points": None}


def test_repetir_o_mesmo_valor_nao_gera_auditoria(cenario, prio):
    h = criar_historia(cenario, story_points=5)
    prio.definir_story_points(cenario.dono, h.id, 5)
    assert auditoria(cenario.conn, "historia", "ALTERAR") == []


# ---------- MoSCoW ----------


@pytest.mark.parametrize("entrada,esperado", [("M", "M"), ("s", "S"), (" c ", "C"), ("w", "W")])
def test_atribui_etiqueta_normalizando_caixa_e_espacos(cenario, prio, entrada, esperado):
    h = criar_historia(cenario, moscow="W" if esperado != "W" else "M")
    assert prio.definir_moscow(cenario.dono, h.id, entrada).moscow == esperado


@pytest.mark.parametrize("entrada", ["X", "MS", "", "   ", None])
def test_etiqueta_invalida_ou_vazia_mantem_a_atual(cenario, prio, entrada):
    h = criar_historia(cenario, moscow="C")
    with pytest.raises(ErroDeValidacao) as erro:
        prio.definir_moscow(cenario.dono, h.id, entrada)
    assert set(erro.value.erros) == {"moscow"}
    assert cenario.historias.obter(cenario.dono, h.id).moscow == "C"


def test_moscow_audita_antes_e_depois(cenario, prio):
    h = criar_historia(cenario, moscow="S")
    prio.definir_moscow(cenario.dono, h.id, "M")
    (linha,) = auditoria(cenario.conn, "historia", "ALTERAR")
    assert linha.valor_anterior == {"moscow": "S"} and linha.valor_posterior == {"moscow": "M"}


# ---------- RICE ----------


def test_historia_nova_nao_tem_rice(cenario):
    h = criar_historia(cenario)
    assert (h.rice, h.rice_reach, h.rice_impact, h.rice_confidence, h.rice_effort) == (None,) * 5


def test_grava_as_entradas_e_a_nota_sai_calculada(cenario, prio):
    h = criar_historia(cenario)
    r = prio.definir_rice(cenario.dono, h.id, 1000, 2, 80, 5)
    assert (r.rice_reach, r.rice_impact, r.rice_confidence, r.rice_effort) == (1000, Decimal(2), 80, 5)
    assert r.rice == Decimal("320.00")
    # "volto depois e vejo os mesmos valores" (US-17), inclusive pelas leituras da lista e do obter
    assert cenario.historias.obter(cenario.dono, h.id).rice == Decimal("320.00")
    (da_lista,) = cenario.historias.listar(cenario.dono, cenario.projeto)
    assert da_lista.rice_impact == Decimal("2") and da_lista.rice == Decimal("320.00")


def test_impact_fracionario_e_gravado_e_lido_sem_perda(cenario, prio):
    h = criar_historia(cenario)
    r = prio.definir_rice(cenario.dono, h.id, 500, "0,25", 50, 8)
    assert r.rice_impact == Decimal("0.25") and r.rice == Decimal("7.81")  # 500×0,25×0,5/8 = 7,8125


def test_rice_nao_e_gravado_so_as_entradas(cenario, prio):
    h = criar_historia(cenario)
    prio.definir_rice(cenario.dono, h.id, 1000, 2, 80, 5)
    colunas = {c for (c,) in cenario.conn.exec_driver_sql(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'historia'")}
    assert {"rice_reach", "rice_impact", "rice_confidence", "rice_effort"} <= colunas
    assert not {c for c in colunas if "nota" in c or c in ("rice", "rice_score", "rice_pontuacao")}


def test_alterar_uma_entrada_recalcula_a_nota(cenario, prio):
    h = criar_historia(cenario)
    prio.definir_rice(cenario.dono, h.id, 1000, 2, 80, 5)
    r = prio.definir_rice(cenario.dono, h.id, 1000, 2, 80, 8)
    assert r.rice == Decimal("200.00")


@pytest.mark.parametrize("entradas,campos", [
    ((1000, 2, 80, 0), {"rice_effort"}),
    ((1000, 9, 80, 5), {"rice_impact"}),
    ((1000, 2, 70, 5), {"rice_confidence"}),
    ((-1, 2, 80, 5), {"rice_reach"}),
    ((None, 2, 80, 5), {"rice_reach"}),
    ((1000, None, None, None), {"rice_impact", "rice_confidence", "rice_effort"}),
])
def test_rice_invalido_ou_incompleto_nao_grava_nada(cenario, prio, entradas, campos):
    h = criar_historia(cenario)
    with pytest.raises(ErroDeValidacao) as erro:
        prio.definir_rice(cenario.dono, h.id, *entradas)
    assert set(erro.value.erros) == campos
    assert cenario.historias.obter(cenario.dono, h.id).rice_reach is None  # nem a parte válida
    assert auditoria(cenario.conn, "historia", "ALTERAR") == []


def test_rice_invalido_preserva_o_rice_anterior(cenario, prio):
    h = criar_historia(cenario)
    prio.definir_rice(cenario.dono, h.id, 1000, 2, 80, 5)
    with pytest.raises(ErroDeValidacao):
        prio.definir_rice(cenario.dono, h.id, 1, 2, 80, 0)
    assert cenario.historias.obter(cenario.dono, h.id).rice == Decimal("320.00")


def test_rice_audita_entradas_antes_e_depois(cenario, prio):
    h = criar_historia(cenario)
    prio.definir_rice(cenario.dono, h.id, 1000, 2, 80, 5)
    prio.definir_rice(cenario.dono, h.id, 1000, 0.5, 80, 5)
    primeira, segunda = auditoria(cenario.conn, "historia", "ALTERAR")
    assert primeira.valor_anterior == dict.fromkeys(
        ("rice_reach", "rice_impact", "rice_confidence", "rice_effort"))
    assert primeira.valor_posterior == {
        "rice_reach": 1000, "rice_impact": 2, "rice_confidence": 80, "rice_effort": 5}
    assert segunda.valor_anterior["rice_impact"] == 2 and segunda.valor_posterior["rice_impact"] == 0.5


def test_repetir_o_mesmo_rice_nao_gera_auditoria(cenario, prio):
    h = criar_historia(cenario)
    prio.definir_rice(cenario.dono, h.id, 1000, 0.5, 80, 5)
    prio.definir_rice(cenario.dono, h.id, 1000, "0,5", 80, 5)  # mesmo valor, outra grafia
    assert len(auditoria(cenario.conn, "historia", "ALTERAR")) == 1


def test_limpar_remove_as_quatro_entradas_juntas(cenario, prio):
    h = criar_historia(cenario)
    prio.definir_rice(cenario.dono, h.id, 1000, 2, 80, 5)
    r = prio.limpar_rice(cenario.dono, h.id)
    assert (r.rice, r.rice_reach, r.rice_impact, r.rice_confidence, r.rice_effort) == (None,) * 5
    assert len(auditoria(cenario.conn, "historia", "ALTERAR")) == 2


def test_limpar_sem_rice_nao_gera_auditoria(cenario, prio):
    h = criar_historia(cenario)
    prio.limpar_rice(cenario.dono, h.id)
    assert auditoria(cenario.conn, "historia", "ALTERAR") == []


def test_previa_da_nota_nao_grava(cenario, prio):
    h = criar_historia(cenario)
    assert prio.calcular_rice(1000, 2, 80, 5) == Decimal("320.00")
    assert cenario.historias.obter(cenario.dono, h.id).rice is None


# ---------- independência entre as dimensões ----------


def test_pontos_moscow_e_rice_sao_independentes(cenario, prio):
    h = criar_historia(cenario, story_points=5, moscow="M")
    prio.definir_rice(cenario.dono, h.id, 1000, 2, 80, 5)
    prio.definir_story_points(cenario.dono, h.id, 13)
    prio.definir_moscow(cenario.dono, h.id, "C")
    atual = cenario.historias.obter(cenario.dono, h.id)
    assert (atual.story_points, atual.moscow, atual.rice) == (13, "C", Decimal("320.00"))
    prio.limpar_rice(cenario.dono, h.id)
    atual = cenario.historias.obter(cenario.dono, h.id)
    assert (atual.story_points, atual.moscow, atual.rice) == (13, "C", None)


def test_editar_a_historia_no_formulario_nao_apaga_o_rice(cenario, prio):
    h = criar_historia(cenario)
    prio.definir_rice(cenario.dono, h.id, 1000, 2, 80, 5)
    cenario.historias.atualizar(cenario.dono, h.id, "novo papel", "nova ação", "novo benefício", 3, "M")
    assert cenario.historias.obter(cenario.dono, h.id).rice == Decimal("320.00")


# ---------- acesso ----------


@pytest.mark.parametrize("operacao", [
    lambda p, u, h: p.definir_story_points(u, h, 5),
    lambda p, u, h: p.definir_moscow(u, h, "M"),
    lambda p, u, h: p.definir_rice(u, h, 1000, 2, 80, 5),
    lambda p, u, h: p.limpar_rice(u, h),
])
def test_quem_nao_tem_acesso_ao_projeto_nao_encontra_a_historia(cenario, prio, operacao):
    h = criar_historia(cenario, story_points=3, moscow="S")
    with pytest.raises(HistoriaNaoEncontrada):
        operacao(prio, cenario.outro, h.id)
    atual = cenario.historias.obter(cenario.dono, h.id)
    assert (atual.story_points, atual.moscow, atual.rice) == (3, "S", None)
    assert auditoria(cenario.conn, "historia", "ALTERAR") == []


def test_historia_inexistente(cenario, prio):
    with pytest.raises(HistoriaNaoEncontrada):
        prio.definir_rice(cenario.dono, 999999, 1000, 2, 80, 5)


def test_validacao_vem_antes_do_acesso_nao_vaza_existencia(cenario, prio):
    # Entrada inválida é erro de formulário, independente da história existir.
    with pytest.raises(ErroDeValidacao):
        prio.definir_moscow(cenario.outro, 999999, "Z")
