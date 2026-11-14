"""Movimentação de histórias entre backlogs (requisito 8, US-08)."""
from dataclasses import replace
from decimal import Decimal

import pytest
from sqlalchemy import text

from sgr.services.auth_service import ErroDeValidacao
from sgr.services.backlog_service import BacklogNaoEncontrado, BacklogService, SprintEncerrado
from sgr.services.historia_service import HistoriaNaoEncontrada
from sgr.services.priorizacao_service import PriorizacaoService
from tests.fabricas import auditoria, cenario, criar_historia, novo_projeto, novo_usuario, um  # noqa: F401


@pytest.fixture()
def backlogs(cenario):
    return BacklogService(cenario.historias._sessao)


def sprint(c, nome="Sprint 1", estado="PLANEJADO", projeto=None):
    return um(
        c.conn,
        "INSERT INTO backlog (projeto_id, tipo, nome, data_inicio, data_fim, estado) "
        "VALUES (:p, 'SPRINT', :n, '2026-10-01', '2026-10-14', :e) RETURNING id",
        p=projeto or c.projeto, n=nome, e=estado,
    )


def onde_estao(c, backlogs, backlog_id):
    return sorted(h.codigo for h in backlogs.listar_historias(c.dono, backlog_id))


# ---------- o caminho feliz (US-08) ----------


def test_move_do_product_backlog_para_um_sprint(cenario, backlogs):
    h = criar_historia(cenario, story_points=5)
    s = sprint(cenario)
    r = backlogs.mover_historias(cenario.dono, [h.id], s)
    assert r.codigos == (h.codigo,) and r.ja_no_destino == ()
    assert (r.destino.id, r.destino.historias, r.destino.pontos) == (s, 1, 5)
    assert onde_estao(cenario, backlogs, s) == [h.codigo]
    assert onde_estao(cenario, backlogs, cenario.product) == []
    assert cenario.historias.obter(cenario.dono, h.id).backlog_id == s


def test_move_varias_de_uma_vez_e_o_contador_do_destino_acompanha(cenario, backlogs):
    a, b, c = (criar_historia(cenario, story_points=p) for p in (3, 5, 8))
    s = sprint(cenario)
    r = backlogs.mover_historias(cenario.dono, [a.id, b.id], s)
    assert r.codigos == (a.codigo, b.codigo)
    assert (r.destino.historias, r.destino.pontos) == (2, 8)
    assert onde_estao(cenario, backlogs, cenario.product) == [c.codigo]


def test_aceita_qualquer_iteravel_e_ignora_repeticao(cenario, backlogs):
    a, b = criar_historia(cenario), criar_historia(cenario)
    s = sprint(cenario)
    r = backlogs.mover_historias(cenario.dono, (i for i in [a.id, b.id, a.id]), s)
    assert len(r.movidas) == 2


def test_vai_e_volta_entre_product_e_sprints(cenario, backlogs):
    h = criar_historia(cenario)
    s1, s2 = sprint(cenario, "Sprint 1"), sprint(cenario, "Sprint 2")
    for destino in (s1, s2, cenario.product, s2):  # product → sprint → sprint → product → sprint
        assert backlogs.mover_historias(cenario.dono, [h.id], destino).destino.id == destino
    assert cenario.historias.obter(cenario.dono, h.id).backlog_id == s2


# ---------- nada se perde (critério de aceitação central da US-08) ----------


def test_preserva_codigo_criterios_pontos_etiqueta_rice_e_epicos(cenario, backlogs):
    epico = cenario.epicos.criar(cenario.dono, cenario.projeto, "Acesso")
    h = criar_historia(cenario, story_points=8, moscow="M", epicos_ids=[epico.id])
    cenario.criterios.criar(cenario.dono, h.id, "estou logado", "crio projeto", "ele aparece")
    cenario.criterios.criar(cenario.dono, h.id, "sem login", "abro o sistema", "vejo o login")
    PriorizacaoService(cenario.historias._sessao).definir_rice(cenario.dono, h.id, 1000, 2, 80, 5)
    antes = cenario.historias.obter(cenario.dono, h.id)
    criterios_antes = cenario.criterios.listar(cenario.dono, h.id)

    s = sprint(cenario)
    backlogs.mover_historias(cenario.dono, [h.id], s)
    backlogs.mover_historias(cenario.dono, [h.id], cenario.product)
    backlogs.mover_historias(cenario.dono, [h.id], s)

    depois = cenario.historias.obter(cenario.dono, h.id)
    # tudo igual, exceto onde a história está
    outros = dict(backlog_id=s, backlog_nome=depois.backlog_nome, backlog_tipo="SPRINT")
    assert replace(antes, **outros) == depois
    assert (depois.codigo, depois.story_points, depois.moscow) == (antes.codigo, 8, "M")
    assert depois.rice == Decimal("320.00") and [e.id for e in depois.epicos] == [epico.id]
    assert cenario.criterios.listar(cenario.dono, h.id) == criterios_antes and len(criterios_antes) == 2


def test_o_identificador_nao_muda_e_a_numeracao_continua(cenario, backlogs):
    a = criar_historia(cenario)
    backlogs.mover_historias(cenario.dono, [a.id], sprint(cenario))
    b = criar_historia(cenario)  # nasce no product, numeração do projeto segue
    assert (a.codigo, b.codigo) == ("SGR-1", "SGR-2")
    assert cenario.historias.obter(cenario.dono, a.id).codigo == "SGR-1"


def test_so_o_backlog_da_historia_muda_no_banco(cenario, backlogs):
    h = criar_historia(cenario)
    colunas = "id, projeto_id, codigo, papel, acao, beneficio, story_points, moscow, " \
              "rice_reach, rice_impact, rice_confidence, rice_effort"
    antes = cenario.conn.execute(text(f"SELECT {colunas} FROM historia WHERE id=:i"), {"i": h.id}).one()
    backlogs.mover_historias(cenario.dono, [h.id], sprint(cenario))
    depois = cenario.conn.execute(text(f"SELECT {colunas} FROM historia WHERE id=:i"), {"i": h.id}).one()
    assert antes == depois


# ---------- auditoria ----------


def test_audita_cada_historia_com_backlog_de_origem_e_de_destino(cenario, backlogs):
    a, b = criar_historia(cenario), criar_historia(cenario)
    s1, s2 = sprint(cenario, "S1"), sprint(cenario, "S2")
    backlogs.mover_historias(cenario.dono, [a.id, b.id], s1)
    backlogs.mover_historias(cenario.dono, [b.id], s2)
    linhas = auditoria(cenario.conn, "historia", "ALTERAR")
    assert [(l.entidade_id, l.valor_anterior, l.valor_posterior) for l in linhas] == [
        (a.id, {"backlog_id": cenario.product}, {"backlog_id": s1}),
        (b.id, {"backlog_id": cenario.product}, {"backlog_id": s1}),
        (b.id, {"backlog_id": s1}, {"backlog_id": s2}),
    ]


# ---------- história que já está no destino ----------


def test_historias_que_ja_estao_no_destino_sao_ignoradas_e_informadas(cenario, backlogs):
    a, b = criar_historia(cenario), criar_historia(cenario)
    s = sprint(cenario)
    backlogs.mover_historias(cenario.dono, [a.id], s)
    r = backlogs.mover_historias(cenario.dono, [a.id, b.id], s)
    assert r.codigos == (b.codigo,) and r.ja_no_destino == (a.codigo,)
    assert len(auditoria(cenario.conn, "historia", "ALTERAR")) == 2  # a não foi auditada de novo


def test_se_nenhuma_muda_e_erro_e_nada_e_gravado(cenario, backlogs):
    h = criar_historia(cenario)
    with pytest.raises(ErroDeValidacao) as erro:
        backlogs.mover_historias(cenario.dono, [h.id], cenario.product)
    assert set(erro.value.erros) == {"destino"} and "Product Backlog" in erro.value.erros["destino"]
    assert auditoria(cenario.conn, "historia", "ALTERAR") == []


# ---------- sprint encerrado é somente leitura ----------


@pytest.mark.parametrize("estado", ["PLANEJADO", "EM_ANDAMENTO"])
def test_sprint_planejado_ou_em_andamento_recebe_historias(cenario, backlogs, estado):
    h = criar_historia(cenario)
    s = sprint(cenario, estado=estado)
    assert backlogs.mover_historias(cenario.dono, [h.id], s).destino.estado == estado


def test_sprint_encerrado_nao_recebe_historias(cenario, backlogs):
    h = criar_historia(cenario)
    encerrado = sprint(cenario, "Sprint 11", estado="ENCERRADO")
    with pytest.raises(SprintEncerrado) as erro:
        backlogs.mover_historias(cenario.dono, [h.id], encerrado)
    assert erro.value.destino and "Sprint 11" in str(erro.value) and "somente leitura" in str(erro.value)
    assert cenario.historias.obter(cenario.dono, h.id).backlog_id == cenario.product
    assert auditoria(cenario.conn, "historia", "ALTERAR") == []


def test_sprint_encerrado_nao_libera_historias(cenario, backlogs):
    h = criar_historia(cenario)
    s = sprint(cenario, "Sprint 11")
    backlogs.mover_historias(cenario.dono, [h.id], s)
    cenario.conn.execute(text("UPDATE backlog SET estado='ENCERRADO' WHERE id=:i"), {"i": s})
    with pytest.raises(SprintEncerrado) as erro:
        backlogs.mover_historias(cenario.dono, [h.id], cenario.product)
    assert not erro.value.destino and h.codigo in str(erro.value)
    assert cenario.historias.obter(cenario.dono, h.id).backlog_id == s


def test_sprint_encerrado_aparece_como_somente_leitura_para_a_interface(cenario, backlogs):
    sprint(cenario, "Aberto")
    sprint(cenario, "Sprint 11", estado="ENCERRADO")
    por_nome = {b.nome: b for b in backlogs.listar(cenario.dono, cenario.projeto).sprints}
    assert not por_nome["Aberto"].somente_leitura and por_nome["Sprint 11"].somente_leitura


# ---------- tudo ou nada ----------


def test_uma_historia_inexistente_cancela_a_movimentacao_inteira(cenario, backlogs):
    a, b = criar_historia(cenario), criar_historia(cenario)
    s = sprint(cenario)
    with pytest.raises(HistoriaNaoEncontrada):
        backlogs.mover_historias(cenario.dono, [a.id, b.id, 999999], s)
    assert onde_estao(cenario, backlogs, s) == []
    assert auditoria(cenario.conn, "historia", "ALTERAR") == []


def test_uma_historia_em_sprint_encerrado_cancela_as_demais(cenario, backlogs):
    livre, presa = criar_historia(cenario), criar_historia(cenario)
    velho = sprint(cenario, "Velho")
    backlogs.mover_historias(cenario.dono, [presa.id], velho)
    cenario.conn.execute(text("UPDATE backlog SET estado='ENCERRADO' WHERE id=:i"), {"i": velho})
    novo = sprint(cenario, "Novo")
    with pytest.raises(SprintEncerrado):
        backlogs.mover_historias(cenario.dono, [livre.id, presa.id], novo)
    assert onde_estao(cenario, backlogs, novo) == []  # nem a história livre foi movida


# ---------- seleção ----------


@pytest.mark.parametrize("selecao", [[], (), set(), iter(())])
def test_selecao_vazia(cenario, backlogs, selecao):
    with pytest.raises(ErroDeValidacao) as erro:
        backlogs.mover_historias(cenario.dono, selecao, sprint(cenario))
    assert set(erro.value.erros) == {"historias"} and "ao menos uma" in erro.value.erros["historias"]


@pytest.mark.parametrize("selecao", [[None], [True], ["1"], [1.5], ["SGR-1"]])
def test_selecao_com_valor_que_nao_e_id(cenario, backlogs, selecao):
    with pytest.raises(ErroDeValidacao) as erro:
        backlogs.mover_historias(cenario.dono, selecao, sprint(cenario))
    assert set(erro.value.erros) == {"historias"}


# ---------- acesso e projeto ----------


def test_quem_nao_tem_acesso_nao_encontra_nem_o_destino_nem_as_historias(cenario, backlogs):
    h = criar_historia(cenario)
    s = sprint(cenario)
    with pytest.raises(BacklogNaoEncontrado):
        backlogs.mover_historias(cenario.outro, [h.id], s)
    # destino próprio do "outro", mas a história é do dono
    projeto_outro, product_outro = novo_projeto(cenario.conn, cenario.outro, "Do outro")
    with pytest.raises(HistoriaNaoEncontrada):
        backlogs.mover_historias(cenario.outro, [h.id], product_outro)
    assert cenario.historias.obter(cenario.dono, h.id).backlog_id == cenario.product
    assert auditoria(cenario.conn, "historia", "ALTERAR") == []


def test_membro_do_projeto_pode_mover(cenario, backlogs):
    h = criar_historia(cenario)
    s = sprint(cenario)
    cenario.conn.execute(
        text("INSERT INTO projeto_membro (projeto_id, usuario_id) VALUES (:p, :u)"),
        {"p": cenario.projeto, "u": cenario.outro},
    )
    assert backlogs.mover_historias(cenario.outro, [h.id], s).codigos == (h.codigo,)
    (linha,) = auditoria(cenario.conn, "historia", "ALTERAR")
    assert linha.valor_posterior == {"backlog_id": s}


def test_nao_move_para_backlog_de_outro_projeto_mesmo_com_acesso_aos_dois(cenario, backlogs):
    h = criar_historia(cenario)
    segundo, _ = novo_projeto(cenario.conn, cenario.dono, "Segundo")
    sprint_do_segundo = sprint(cenario, projeto=segundo)
    with pytest.raises(ErroDeValidacao) as erro:
        backlogs.mover_historias(cenario.dono, [h.id], sprint_do_segundo)
    assert set(erro.value.erros) == {"destino"} and "mesmo projeto" in erro.value.erros["destino"]
    assert cenario.historias.obter(cenario.dono, h.id).backlog_id == cenario.product


def test_destino_inexistente(cenario, backlogs):
    h = criar_historia(cenario)
    with pytest.raises(BacklogNaoEncontrado):
        backlogs.mover_historias(cenario.dono, [h.id], 999999)
