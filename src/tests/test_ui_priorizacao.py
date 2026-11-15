"""Telas de priorização (issue #34, Storyboard 5, Q-32 a Q-40)."""
from collections import Counter

from datetime import date

import pytest
from sqlalchemy import text
from streamlit.testing.v1 import AppTest

from sgr.db import session as db_session
from sgr.services import autenticacao, backlogs, epicos, historias, priorizacao, projetos
from sgr.ui import navegacao


# ---------- infraestrutura ----------

def _pagina():
    from sgr.ui.pagina_priorizacao import pagina_priorizacao

    pagina_priorizacao()


def _dialogo(nome, projeto_id, historia_id):
    """Abre o diálogo em todo run (o AppTest reexecuta o script inteiro a cada interação)."""
    from collections import Counter

    from sgr.services import historias
    from sgr.ui import priorizacao_form as form
    from sgr.ui.sessao import usuario_logado

    u = usuario_logado()
    todas = historias.listar(u.id, projeto_id)
    h = historias.obter(u.id, historia_id)
    if nome == "pontos":
        form.dialogo_pontos(u.id, h, form.sugestao_pontos(h, todas))
    elif nome == "moscow":
        form.dialogo_moscow(u.id, h, dict(Counter(o.moscow for o in todas)))
    elif nome == "rice":
        form.dialogo_rice(u.id, h)


def _dialogo_lote(nome, projeto_id, ids):
    """Diálogos que agem sobre uma seleção de histórias (`ids`)."""
    from sgr.services import backlogs, historias
    from sgr.ui import priorizacao_form as form
    from sgr.ui.sessao import usuario_logado

    u = usuario_logado()
    selecionadas = [historias.obter(u.id, i) for i in ids]
    if nome == "lote":
        form.dialogo_pontos_em_lote(u.id, selecionadas)
    elif nome == "mover":
        conjunto = backlogs.listar(u.id, projeto_id)
        form.dialogo_mover(u.id, selecionadas, ([conjunto.product] if conjunto.product else []) + conjunto.sprints)


@pytest.fixture()
def ctx(engine, test_url, monkeypatch):
    """Ana com um projeto que já tem product backlog."""
    monkeypatch.setenv("DATABASE_URL", test_url)
    db_session.get_engine.cache_clear()
    db_session._session_factory.cache_clear()
    monkeypatch.setattr(autenticacao, "_rounds", 4)

    def limpar():
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE usuario RESTART IDENTITY CASCADE"))
            conn.execute(text("TRUNCATE registro_auditoria"))

    limpar()
    ana = autenticacao.cadastrar("Ana", "ana@x.com", "senha-segura-123", "senha-segura-123")
    projeto = projetos.criar(ana.id, "Portal do Cliente")
    backlogs.criar_product(ana.id, projeto.id, "Product Backlog")
    yield ana, projeto
    limpar()
    db_session.get_engine.cache_clear()
    db_session._session_factory.cache_clear()


def _tela(usuario, script=_pagina, args=(), estado=None) -> AppTest:
    at = AppTest.from_function(script, args=args, default_timeout=20)
    at.session_state["usuario_autenticado"] = usuario
    for chave, valor in (estado or {}).items():
        at.session_state[chave] = valor
    return at.run()


def _dialogo_aberto(ana, nome, projeto, historia) -> AppTest:
    return _tela(ana, _dialogo, args=(nome, projeto.id, historia.id))


def _hist(ana, projeto, acao, pontos=None, moscow="S", rice=None, **kw):
    h = historias.criar(ana.id, projeto.id, papel="cliente", acao=acao, beneficio="ganhar tempo",
                        story_points=pontos, moscow=moscow, **kw)
    if rice:
        h = priorizacao.definir_rice(ana.id, h.id, *rice)
    return h


def _ordem(at, lista) -> list[str]:
    """Códigos das histórias na ordem em que aparecem na tabela."""
    valores = [m.value for m in at.markdown]
    achados = []
    for v in valores:
        for h in lista:
            if v.startswith(f"**{h.codigo}** ·"):
                achados.append(h.codigo)
    return achados


def _texto(at) -> str:
    return " ".join([m.value for m in at.markdown] + [c.value for c in at.caption])


# ---------- Q-32: tabela, filtros e ordenação ----------

def test_exige_login():
    at = AppTest.from_function(_pagina, default_timeout=20).run()
    assert any("Faça login" in e.value for e in at.error)


def test_ordena_por_rice_com_pendentes_no_fim_e_inverte(ctx):
    ana, p = ctx
    a = _hist(ana, p, "ver a", rice=(100, 2, 50, 5))  # 20
    b = _hist(ana, p, "ver b", rice=(100, 3, 100, 1))  # 300
    c = _hist(ana, p, "ver c", rice=(10, 1, 100, 1))  # 10
    d = _hist(ana, p, "ver d")  # sem RICE
    todas = [a, b, c, d]
    at = _tela(ana)
    assert not at.exception
    assert _ordem(at, todas) == [b.codigo, a.codigo, c.codigo, d.codigo]
    at.toggle(key="flt_prio_inverter").set_value(True).run()
    assert _ordem(at, todas) == [c.codigo, a.codigo, b.codigo, d.codigo]  # sem RICE continua por último


def test_ordena_por_pontos_moscow_e_titulo(ctx):
    ana, p = ctx
    a = _hist(ana, p, "zebra", pontos=2, moscow="C")
    b = _hist(ana, p, "abelha", pontos=8, moscow="M")
    c = _hist(ana, p, "morcego", pontos=None, moscow="S")
    todas = [a, b, c]
    at = _tela(ana)
    at.selectbox(key="flt_prio_ordem").select("pontos").run()
    assert _ordem(at, todas) == [b.codigo, a.codigo, c.codigo]
    at.selectbox(key="flt_prio_ordem").select("moscow").run()
    assert _ordem(at, todas) == [b.codigo, c.codigo, a.codigo]
    at.selectbox(key="flt_prio_ordem").select("titulo").run()
    assert _ordem(at, todas) == [b.codigo, c.codigo, a.codigo]  # abelha, morcego, zebra
    at.selectbox(key="flt_prio_ordem").select("criacao").run()
    assert _ordem(at, todas) == [a.codigo, b.codigo, c.codigo]


def test_filtros_e_total_de_pontos(ctx):
    ana, p = ctx
    e = epicos.criar(ana.id, p.id, "Catálogo")
    a = _hist(ana, p, "ver a", pontos=5, moscow="M", rice=(10, 1, 100, 1), epicos_ids=[e.id])
    b = _hist(ana, p, "ver b", pontos=3, moscow="S")
    c = _hist(ana, p, "ver c", pontos=8, moscow="W")
    todas = [a, b, c]
    at = _tela(ana)
    assert "3 histórias · 16 pontos" in _texto(at)
    at.multiselect(key="flt_prio_moscow").set_value(["M", "S"]).run()
    assert _ordem(at, todas) == [a.codigo, b.codigo] or set(_ordem(at, todas)) == {a.codigo, b.codigo}
    assert "2 histórias · 8 pontos" in _texto(at)
    at.multiselect(key="flt_prio_moscow").set_value([]).run()
    at.selectbox(key="flt_prio_rice").select(False).run()
    assert set(_ordem(at, todas)) == {b.codigo, c.codigo}
    at.selectbox(key="flt_prio_rice").select(None).run()
    at.selectbox(key="flt_prio_epico").select(e.id).run()
    assert _ordem(at, todas) == [a.codigo]
    at.button(key="btn_limpar_filtros_priorizacao").click().run()
    assert len(_ordem(at, todas)) == 3


def test_sem_historias_e_filtro_sem_resultado(ctx):
    ana, p = ctx
    at = _tela(ana)
    assert any("ainda não tem histórias" in c.value for c in at.caption)
    _hist(ana, p, "ver a", moscow="M")
    at = _tela(ana)
    at.multiselect(key="flt_prio_moscow").set_value(["W"]).run()
    assert any("Nenhuma história com esses filtros" in c.value for c in at.caption)


def test_marca_historia_alterada(ctx):
    ana, p = ctx
    h = _hist(ana, p, "ver a")
    at = _tela(ana, estado={navegacao.HISTORIA_ALTERADA: h.id})
    assert any("*(alterada)*" in m.value for m in at.markdown)
    at.run()  # a marca vale uma vez
    assert not any("*(alterada)*" in m.value for m in at.markdown)


# ---------- Q-36: agrupar por MoSCoW ----------

def test_agrupa_por_moscow_e_resume_a_faixa_fora_do_filtro(ctx):
    ana, p = ctx
    _hist(ana, p, "ver a", pontos=5, moscow="M")
    _hist(ana, p, "ver b", pontos=3, moscow="M")
    _hist(ana, p, "ver c", pontos=8, moscow="S")
    _hist(ana, p, "ver d", pontos=2, moscow="W")
    at = _tela(ana)
    at.toggle(key="flt_prio_agrupar").set_value(True).run()
    at.multiselect(key="flt_prio_moscow").set_value(["M", "S"]).run()
    corpo = _texto(at)
    assert "Must have (2 histórias)" in corpo and "Should have (1 história)" in corpo
    assert "Won't have (" not in corpo
    assert "M: 2 · 8 pts" in corpo and "S: 1 · 8 pts" in corpo
    assert "W: 1 · 2 pts — fora do filtro" in corpo


# ---------- Q-33/Q-34: story points ----------

def test_sugestao_usa_a_media_das_ultimas_tres_do_epico(ctx):
    ana, p = ctx
    e = epicos.criar(ana.id, p.id, "Catálogo")
    for pts in (13, 5, 5, 5):  # só as três últimas entram: média 5
        _hist(ana, p, f"ver {pts}", pontos=pts, epicos_ids=[e.id])
    alvo = _hist(ana, p, "alvo", epicos_ids=[e.id])
    from sgr.ui.priorizacao_form import sugestao_pontos

    todas = historias.listar(ana.id, p.id)
    assert sugestao_pontos(alvo, todas) == "Sugestão do sistema: a média das últimas 3 histórias estimadas do épico Catálogo é 5 pontos."
    sem_epico = _hist(ana, p, "solta")
    assert sugestao_pontos(sem_epico, todas) is None


def test_sugestao_com_media_fora_da_escala(ctx):
    ana, p = ctx
    e = epicos.criar(ana.id, p.id, "Catálogo")
    _hist(ana, p, "a", pontos=3, epicos_ids=[e.id])
    _hist(ana, p, "b", pontos=2, epicos_ids=[e.id])
    alvo = _hist(ana, p, "alvo", epicos_ids=[e.id])
    from sgr.ui.priorizacao_form import sugestao_pontos

    texto = sugestao_pontos(alvo, historias.listar(ana.id, p.id))
    assert "2,5 pontos (valor mais próximo da escala: 2)" in texto


def test_dialogo_pontos_mostra_escala_e_sugestao_e_salva(ctx):
    ana, p = ctx
    e = epicos.criar(ana.id, p.id, "Catálogo")
    for pts in (5, 5, 5):
        _hist(ana, p, f"ver {pts}", pontos=pts, epicos_ids=[e.id])
    alvo = _hist(ana, p, "alvo", epicos_ids=[e.id])
    at = _dialogo_aberto(ana, "pontos", p, alvo)
    assert not at.exception
    radio = at.radio(key=f"pt{alvo.id}_valor")
    assert list(radio.options) == ["0", "1", "2", "3", "5", "8", "13", "21", "34", "55"]  # escala fechada
    assert any("média das últimas 3 histórias" in i.value for i in at.info)
    radio.set_value(8)
    at.button(key=f"pt{alvo.id}_salvar").click().run()
    assert historias.obter(ana.id, alvo.id).story_points == 8
    assert "8 pontos" in at.session_state[navegacao.AVISO_PRIORIZACAO]


def test_dialogo_pontos_sem_escolha_mostra_erro_e_nao_grava(ctx):
    ana, p = ctx
    alvo = _hist(ana, p, "alvo")
    at = _dialogo_aberto(ana, "pontos", p, alvo)
    at.button(key=f"pt{alvo.id}_salvar").click().run()
    assert any("Selecione um valor da escala" in e.value for e in at.error)
    assert historias.obter(ana.id, alvo.id).story_points is None


# ---------- Q-35: MoSCoW ----------

def test_dialogo_moscow_mostra_contagens_e_salva(ctx):
    ana, p = ctx
    alvo = _hist(ana, p, "alvo", moscow="S")
    _hist(ana, p, "outra", moscow="M")
    at = _dialogo_aberto(ana, "moscow", p, alvo)
    assert not at.exception
    radio = at.radio(key=f"ms{alvo.id}_valor")
    assert radio.value == "S"
    corpo = " ".join(radio.proto.captions)
    assert "obrigatório neste escopo · 1 história" in corpo and "importante, mas não bloqueia · 1 história" in corpo
    assert "fora deste escopo, registrado para depois · 0 história" in corpo
    radio.set_value("M")
    at.button(key=f"ms{alvo.id}_salvar").click().run()
    assert historias.obter(ana.id, alvo.id).moscow == "M"
    assert "Must have" in at.session_state[navegacao.AVISO_PRIORIZACAO]


# ---------- Q-37 a Q-39: RICE ----------

def _preencher_rice(at, h, reach=100, impacto=2, confianca=80, esforco=5):
    p = f"rc{h.id}_"
    at.number_input(key=p + "reach").set_value(reach)
    at.radio(key=p + "impact").set_value(__import__("decimal").Decimal(str(impacto)))
    at.radio(key=p + "confidence").set_value(confianca)
    at.radio(key=p + "effort").set_value(esforco)
    return at.run()


def test_dialogo_rice_calcula_na_hora_e_salva(ctx):
    ana, p = ctx
    alvo = _hist(ana, p, "alvo")
    at = _dialogo_aberto(ana, "rice", p, alvo)
    assert not at.exception
    assert any("aguardando valores válidos" in c.value for c in at.caption)  # nada a calcular ainda
    at = _preencher_rice(at, alvo)
    corpo = _texto(at)
    assert "### 32" in corpo and "(100 × 2 × 80%) / 5 = 32" in corpo
    at.button(key=f"rc{alvo.id}_salvar").click().run()
    salvo = historias.obter(ana.id, alvo.id)
    assert salvo.rice == 32 and (salvo.rice_reach, salvo.rice_confidence, salvo.rice_effort) == (100, 80, 5)
    assert navegacao.AVISO_PRIORIZACAO in at.session_state


def test_dialogo_rice_mostra_variacao_e_marca_alterada(ctx):
    ana, p = ctx
    alvo = _hist(ana, p, "alvo", rice=(100, 2, 80, 5))  # 32
    at = _dialogo_aberto(ana, "rice", p, alvo)
    at.radio(key=f"rc{alvo.id}_effort").set_value(8).run()
    assert any("antes 32 · agora 20 ↓" in c.value for c in at.caption)
    at.button(key=f"rc{alvo.id}_salvar").click().run()
    assert historias.obter(ana.id, alvo.id).rice == 20
    assert "32 → 20 ↓" in at.session_state[navegacao.AVISO_PRIORIZACAO]
    assert at.session_state[navegacao.HISTORIA_ALTERADA] == alvo.id


def test_dialogo_rice_incompleto_mostra_o_erro_no_campo_e_nao_grava(ctx):
    ana, p = ctx
    alvo = _hist(ana, p, "alvo")
    at = _dialogo_aberto(ana, "rice", p, alvo)
    at.number_input(key=f"rc{alvo.id}_reach").set_value(100).run()
    at.button(key=f"rc{alvo.id}_salvar").click().run()
    erros = " ".join(e.value for e in at.error)
    assert "Informe o Impact" in erros and "Informe o Confidence" in erros and "Informe o Effort" in erros
    assert historias.obter(ana.id, alvo.id).rice is None


def test_effort_nao_oferece_zero(ctx):
    ana, p = ctx
    alvo = _hist(ana, p, "alvo")
    at = _dialogo_aberto(ana, "rice", p, alvo)
    assert "0" not in list(at.radio(key=f"rc{alvo.id}_effort").options)
    assert any("O zero não é aceito" in c.value for c in at.caption)


# ---------- Q-40: ordenar e comparar ----------

def test_quadrantes_valor_x_esforco(ctx):
    ana, p = ctx
    rapida = _hist(ana, p, "rapida", rice=(1000, 3, 100, 1))
    grande = _hist(ana, p, "grande", rice=(1000, 3, 100, 55))
    ganho = _hist(ana, p, "ganho", rice=(10, 1, 50, 1))
    pior = _hist(ana, p, "pior", rice=(10, 1, 50, 55))
    _hist(ana, p, "sem rice")
    from sgr.ui.pagina_priorizacao import _quadrantes

    q = _quadrantes(historias.listar(ana.id, p.id))
    assert q == {"fazer agora": [rapida.codigo], "avaliar com calma": [grande.codigo],
                 "ganho rápido": [ganho.codigo], "descartar": [pior.codigo]}


def test_corte_sugerido_e_matriz_na_pagina(ctx):
    ana, p = ctx
    _hist(ana, p, "a", rice=(100, 2, 80, 5))  # 32
    _hist(ana, p, "b", rice=(100, 3, 80, 5))  # 48
    _hist(ana, p, "c", rice=(10, 1, 100, 5))  # 2
    at = _tela(ana)
    assert not at.exception
    corpo = _texto(at)
    assert "corte sugerido: 2 itens acima da média" in corpo  # média 27,33: 32 e 48
    assert "**fazer agora**" in corpo and "**descartar**" in corpo
    at.selectbox(key="flt_prio_ordem").select("pontos").run()
    assert "corte sugerido" not in _texto(at)  # só aparece ao ordenar por RICE


def test_matriz_sem_rice(ctx):
    ana, p = ctx
    _hist(ana, p, "a")
    at = _tela(ana)
    assert any("Nenhuma história com RICE para comparar" in c.value for c in at.caption)


# ---------- seleção, mover e edição em lote ----------

def _sprints(ana, p):
    s12 = backlogs.criar_sprint(ana.id, p.id, "Sprint 12", date(2026, 10, 1), date(2026, 10, 14))
    s13 = backlogs.criar_sprint(ana.id, p.id, "Sprint 13", date(2026, 10, 15), date(2026, 10, 28))
    return s12, s13


def _marcar(at, *historias_):
    for h in historias_:
        at.checkbox(key=f"sel_prio_0_{h.id}").check()
    return at.run()


def test_barra_de_selecao_comeca_desabilitada_e_habilita_ao_marcar(ctx):
    ana, p = ctx
    a, b = _hist(ana, p, "ver a"), _hist(ana, p, "ver b")
    at = _tela(ana)
    assert at.button(key="btn_mover_prio").disabled and at.button(key="btn_lote_prio").disabled
    assert any("Marque a caixa de seleção" in c.value for c in at.caption)
    at = _marcar(at, a, b)
    assert "2 histórias selecionadas" in _texto(at)
    assert not at.button(key="btn_mover_prio").disabled and not at.button(key="btn_lote_prio").disabled
    at.button(key="btn_limpar_selecao_prio").click().run()
    assert at.button(key="btn_mover_prio").disabled
    assert "selecionadas" not in _texto(at)


def test_botoes_da_barra_abrem_os_dialogos(ctx):
    ana, p = ctx
    _sprints(ana, p)
    a = _hist(ana, p, "ver a")
    at = _marcar(_tela(ana), a)
    at.button(key="btn_mover_prio").click().run()
    assert at.radio(key="mvprio_destino") is not None
    at = _marcar(_tela(ana), a)
    at.button(key="btn_lote_prio").click().run()
    assert at.radio(key="ptlote_valor") is not None


def test_mover_exclui_o_backlog_de_origem_e_move_a_selecao(ctx):
    ana, p = ctx
    s12, s13 = _sprints(ana, p)
    a, b = _hist(ana, p, "ver a"), _hist(ana, p, "ver b")
    at = _tela(ana, _dialogo_lote, args=("mover", p.id, [a.id, b.id]))
    assert not at.exception
    radio = at.radio(key="mvprio_destino")
    assert len(radio.options) == 2 and not any(o.startswith("Product Backlog") for o in radio.options)  # sem a origem
    radio.set_value(s13.id)
    at.button(key="mvprio_confirmar").click().run()
    assert {historias.obter(ana.id, h.id).backlog_id for h in (a, b)} == {s13.id}
    assert "2 histórias movidas para Sprint 13" in at.session_state[navegacao.AVISO_PRIORIZACAO]
    assert at.session_state[navegacao.GERACAO_SELECAO_PRIORIZACAO] == 1  # seleção limpa


def test_mover_selecao_de_origens_diferentes(ctx):
    ana, p = ctx
    s12, s13 = _sprints(ana, p)
    a, b = _hist(ana, p, "ver a"), _hist(ana, p, "ver b")
    backlogs.mover_historias(ana.id, [b.id], s12.id)
    at = _tela(ana, _dialogo_lote, args=("mover", p.id, [a.id, b.id]))
    assert len(at.radio(key="mvprio_destino").options) == 3  # product e os dois sprints
    at.radio(key="mvprio_destino").set_value(s13.id)
    at.button(key="mvprio_confirmar").click().run()
    assert {historias.obter(ana.id, h.id).backlog_id for h in (a, b)} == {s13.id}


def test_mover_de_sprint_encerrado_mostra_o_erro_e_nao_move(ctx, engine):
    ana, p = ctx
    s12, s13 = _sprints(ana, p)
    a = _hist(ana, p, "ver a")
    backlogs.mover_historias(ana.id, [a.id], s12.id)
    with engine.begin() as conn:
        conn.execute(text("UPDATE backlog SET estado='ENCERRADO' WHERE id=:i"), {"i": s12.id})
    at = _tela(ana, _dialogo_lote, args=("mover", p.id, [a.id]))
    at.radio(key="mvprio_destino").set_value(s13.id)
    at.button(key="mvprio_confirmar").click().run()
    assert any("encerrado" in e.value for e in at.error)
    assert historias.obter(ana.id, a.id).backlog_id == s12.id


def test_mover_sem_outro_backlog_avisa(ctx):
    ana, p = ctx
    a = _hist(ana, p, "ver a")
    at = _tela(ana, _dialogo_lote, args=("mover", p.id, [a.id]))
    assert any("Não há outro backlog" in w.value for w in at.warning)


def test_lote_aplica_pontos_as_selecionadas(ctx):
    ana, p = ctx
    a, b = _hist(ana, p, "ver a", pontos=2), _hist(ana, p, "ver b")
    at = _tela(ana, _dialogo_lote, args=("lote", p.id, [a.id, b.id]))
    assert not at.exception
    radio = at.radio(key="ptlote_valor")
    assert list(radio.options) == ["0", "1", "2", "3", "5", "8", "13", "21", "34", "55"]
    radio.set_value(13)
    at.button(key="ptlote_aplicar").click().run()
    assert {historias.obter(ana.id, h.id).story_points for h in (a, b)} == {13}
    assert "13 pontos aplicados a 2 histórias" in at.session_state[navegacao.AVISO_PRIORIZACAO]
    assert at.session_state[navegacao.GERACAO_SELECAO_PRIORIZACAO] == 1


def test_lote_sem_valor_mostra_erro_e_nao_grava(ctx):
    ana, p = ctx
    a = _hist(ana, p, "ver a", pontos=2)
    at = _tela(ana, _dialogo_lote, args=("lote", p.id, [a.id]))
    at.button(key="ptlote_aplicar").click().run()
    assert any("Selecione um valor da escala" in e.value for e in at.error)
    assert historias.obter(ana.id, a.id).story_points == 2
