"""Filtro e ordenação da listagem de histórias pela nota RICE.

A nota não é gravada: sai de quatro colunas (services/rice.py). Para filtrar e ordenar no banco a
conta é repetida em SQL (historia_repository.rice_sql); a primeira prova abaixo garante que as
duas coincidem em todo o domínio, com o mesmo arredondamento a duas casas.
"""
from decimal import Decimal

import pytest
from sqlalchemy import select, text

from sgr.repositories import historia_repository
from sgr.services.auth_service import ErroDeValidacao
from sgr.services.rice import CONFIANCAS, ESFORCOS, IMPACTOS, calcular_rice
from tests.fabricas import cenario, criar_historia  # noqa: F401  (fixture reutilizada)

D = Decimal


def _rice(c, historia, reach, impact, confidence, effort):
    c.conn.execute(
        text("UPDATE historia SET rice_reach=:r, rice_impact=:i, rice_confidence=:c, rice_effort=:e WHERE id=:h"),
        {"r": reach, "i": impact, "c": confidence, "e": effort, "h": historia.id},
    )


@pytest.fixture()
def lote(cenario):
    """Cinco histórias: RICE 320, 100, 0.13 (0,125 arredondado), 0 e uma sem RICE."""
    c = cenario
    h = [criar_historia(c, acao=f"ação {i}") for i in range(5)]
    _rice(c, h[0], 1000, 2, 80, 5)  # 320
    _rice(c, h[1], 100, 1, 100, 1)  # 100
    _rice(c, h[2], 1, D("0.25"), 50, 1)  # 0,125 -> 0,13
    _rice(c, h[3], 0, 3, 100, 8)  # 0
    c.h = h  # h[4] fica sem RICE
    return c


def _ids(c, **filtros):
    return [x.id for x in c.historias.listar(c.dono, c.projeto, **filtros)]


# ---------- a conta em SQL é a mesma da fórmula oficial ----------

def test_rice_em_sql_coincide_com_a_formula_em_todo_o_dominio(cenario):
    c = cenario
    reaches = (0, 1, 2, 3, 7, 10, 33, 99, 100, 101, 999, 1000, 12345, 2147483647)
    linhas = [
        {"p": c.projeto, "b": c.product, "c": f"T-{n}", "r": r, "i": i, "cf": cf, "e": e}
        for n, (r, i, cf, e) in enumerate(
            (r, i, cf, e) for r in reaches for i in IMPACTOS for cf in CONFIANCAS for e in ESFORCOS
        )
    ]
    c.conn.execute(
        text(
            "INSERT INTO historia (projeto_id, backlog_id, codigo, papel, acao, beneficio, moscow, "
            "rice_reach, rice_impact, rice_confidence, rice_effort) "
            "VALUES (:p,:b,:c,'p','a','b','S',:r,:i,:cf,:e)"
        ),
        linhas,
    )
    do_banco = dict(
        c.conn.execute(
            select(historia_repository.Historia.codigo, historia_repository.rice_sql()).where(
                historia_repository.Historia.projeto_id == c.projeto
            )
        ).all()
    )
    assert len(do_banco) == len(linhas) == len(reaches) * len(IMPACTOS) * len(CONFIANCAS) * len(ESFORCOS)
    divergentes = [
        (l["c"], do_banco[l["c"]], calcular_rice(l["r"], l["i"], l["cf"], l["e"]))
        for l in linhas
        if do_banco[l["c"]] != calcular_rice(l["r"], l["i"], l["cf"], l["e"])
    ]
    assert divergentes == []


# ---------- filtro ----------

def test_filtro_minimo_e_maximo_sao_inclusivos(lote):
    c, h = lote, lote.h
    assert set(_ids(c, rice_min=100)) == {h[0].id, h[1].id}
    assert set(_ids(c, rice_max=100)) == {h[1].id, h[2].id, h[3].id}
    assert _ids(c, rice_min=100, rice_max=100) == [h[1].id]
    assert _ids(c, rice_min=321) == []


def test_filtro_usa_a_nota_arredondada_que_o_usuario_ve(lote):
    c, h = lote, lote.h
    assert calcular_rice(1, D("0.25"), 50, 1) == D("0.13")
    assert _ids(c, rice_min=D("0.13"), rice_max=D("0.13")) == [h[2].id]
    assert h[2].id not in _ids(c, rice_min=D("0.131"))
    assert h[2].id not in _ids(c, rice_max=D("0.129"))


def test_historia_sem_rice_nunca_passa_por_filtro_de_faixa(lote):
    c, h = lote, lote.h
    assert h[4].id not in _ids(c, rice_min=0)
    assert h[4].id not in _ids(c, rice_max=10**9)
    assert h[3].id in _ids(c, rice_min=0)  # RICE zero é nota válida, diferente de "sem RICE"


def test_com_rice_separa_pontuadas_das_pendentes(lote):
    c, h = lote, lote.h
    assert _ids(c, com_rice=False) == [h[4].id]
    assert set(_ids(c, com_rice=True)) == {h[0].id, h[1].id, h[2].id, h[3].id}
    assert len(_ids(c)) == 5  # sem o filtro, todas


def test_faixa_aceita_texto_com_virgula_e_numeros_de_varios_tipos(lote):
    c, h = lote, lote.h
    assert _ids(c, rice_min="100,0", rice_max="100.00") == [h[1].id]
    assert _ids(c, rice_min=100.0, rice_max=100) == [h[1].id]


def test_faixa_enorme_equivale_a_sem_limite_e_nao_derruba_o_banco(lote):
    c, h = lote, lote.h
    assert set(_ids(c, rice_max=D("1E+300"))) == {h[0].id, h[1].id, h[2].id, h[3].id}
    assert _ids(c, rice_min=D("1E+300")) == []
    assert _ids(c, rice_min="9" * 400) == []


def test_filtro_de_rice_combina_com_os_demais_filtros(lote):
    c, h = lote, lote.h
    epico = c.epicos.criar(c.dono, c.projeto, "Catálogo")
    c.historias.vincular_epico(c.dono, h[0].id, epico.id)
    c.historias.vincular_epico(c.dono, h[3].id, epico.id)
    c.conn.execute(text("UPDATE historia SET moscow='M' WHERE id=:h"), {"h": h[0].id})
    assert _ids(c, epico_id=epico.id, rice_min=1) == [h[0].id]
    assert _ids(c, moscow="M", rice_min=1) == [h[0].id]
    assert _ids(c, moscow="S", rice_min=300) == []
    assert _ids(c, backlog_id=c.product, com_rice=True, rice_max=0) == [h[3].id]


# ---------- ordenação ----------

def test_ordenar_por_rice_e_decrescente_por_padrao_com_pendentes_por_ultimo(lote):
    c, h = lote, lote.h
    assert _ids(c, ordenar_por="rice") == [h[0].id, h[1].id, h[2].id, h[3].id, h[4].id]


def test_ordenar_por_rice_crescente_mantem_pendentes_por_ultimo(lote):
    c, h = lote, lote.h
    assert _ids(c, ordenar_por="rice", ordem="asc") == [h[3].id, h[2].id, h[1].id, h[0].id, h[4].id]


def test_empate_de_rice_desempata_pela_ordem_de_criacao(cenario):
    c = cenario
    h = [criar_historia(c, acao=f"a{i}") for i in range(4)]
    for x in h:
        _rice(c, x, 100, 1, 100, 1)
    assert _ids(c, ordenar_por="rice") == [x.id for x in h]
    assert _ids(c, ordenar_por="rice", ordem="asc") == [x.id for x in h]


def test_ordem_padrao_e_por_posicao_e_aceita_inversao(lote):
    c, h = lote, lote.h
    assert _ids(c) == [x.id for x in h]
    assert _ids(c, ordenar_por="posicao") == [x.id for x in h]
    assert _ids(c, ordenar_por="posicao", ordem="desc") == [x.id for x in reversed(h)]


def test_ordenacao_por_rice_vale_para_a_nota_arredondada(cenario):
    c = cenario
    a, b = criar_historia(c, acao="a"), criar_historia(c, acao="b")
    _rice(c, a, 1, D("0.25"), 50, 1)  # 0,125 -> 0,13
    _rice(c, b, 13, D("0.5"), 100, 55)  # 0,1181... -> 0,12
    assert [x.rice for x in c.historias.listar(c.dono, c.projeto, ordenar_por="rice")] == [D("0.13"), D("0.12")]


def test_a_ordem_devolvida_e_coerente_com_a_nota_exibida(cenario):
    c = cenario
    combinacoes = [(r, i, cf, e) for r in (1, 7, 50, 333) for i in IMPACTOS for cf in (100, 50) for e in (1, 3, 13)]
    for n, comb in enumerate(combinacoes):
        _rice(c, criar_historia(c, acao=f"a{n}"), *comb)
    notas = [x.rice for x in c.historias.listar(c.dono, c.projeto, ordenar_por="rice")]
    assert notas == sorted(notas, reverse=True)
    dentro = [x.rice for x in c.historias.listar(c.dono, c.projeto, rice_min=10, rice_max=100)]
    assert dentro and all(D(10) <= n <= D(100) for n in dentro)
    assert len(dentro) == sum(1 for comb in combinacoes if D(10) <= calcular_rice(*comb) <= D(100))


def test_projeto_alheio_continua_inacessivel(lote):
    from sgr.services.projeto_service import ProjetoNaoEncontrado

    with pytest.raises(ProjetoNaoEncontrado):
        lote.historias.listar(lote.outro, lote.projeto, ordenar_por="rice", rice_min=1)


# ---------- validação ----------

@pytest.mark.parametrize(
    "filtros, campo",
    [
        ({"ordenar_por": "pontos"}, "ordenar_por"),
        ({"ordenar_por": "rice", "ordem": "cima"}, "ordem"),
        ({"rice_min": "abc"}, "rice_min"),
        ({"rice_max": "1,2,3"}, "rice_max"),
        ({"rice_min": -1}, "rice_min"),
        ({"rice_max": D("-0.01")}, "rice_max"),
        ({"rice_min": float("nan")}, "rice_min"),
        ({"rice_max": float("inf")}, "rice_max"),
        ({"rice_min": D("NaN")}, "rice_min"),
        ({"rice_min": True}, "rice_min"),
        ({"rice_min": "1\x00"}, "rice_min"),
        ({"rice_min": 10, "rice_max": 5}, "rice_max"),
        ({"com_rice": "sim"}, "com_rice"),
    ],
)
def test_parametros_invalidos_viram_erro_de_validacao(lote, filtros, campo):
    with pytest.raises(ErroDeValidacao) as e:
        lote.historias.listar(lote.dono, lote.projeto, **filtros)
    assert campo in e.value.erros
