"""Telas de histórias, épicos e critérios de aceitação (issue #33, Storyboard 3, Q-14 a Q-22)."""
import pytest
from sqlalchemy import text
from streamlit.testing.v1 import AppTest

from sgr.db import session as db_session
from sgr.services import autenticacao, backlogs, criterios, epicos, historias, projetos


# ---------- infraestrutura ----------

def _pagina_historias():
    from sgr.ui.pagina_historias import pagina_historias

    pagina_historias()


def _pagina_epicos():
    from sgr.ui.pagina_epicos import pagina_epicos

    pagina_epicos()


def _dialogo(nome, *ids):
    """Abre o diálogo em todo run (o AppTest reexecuta o script inteiro a cada interação)."""
    from sgr.services import criterios, epicos, historias
    from sgr.ui import criterios as ui_criterios
    from sgr.ui import historias_form, pagina_epicos
    from sgr.ui.sessao import usuario_logado

    u = usuario_logado()
    if nome == "nova_historia":
        historias_form.dialogo_historia(u.id, ids[0])
    elif nome == "editar_historia":
        historias_form.dialogo_historia(u.id, ids[0], historias.obter(u.id, ids[1]))
    elif nome == "vincular":
        historias_form.dialogo_epicos(u.id, historias.obter(u.id, ids[0]))
    elif nome == "excluir_historia":
        historias_form.dialogo_exclusao(u.id, historias.obter(u.id, ids[0]))
    elif nome == "novo_criterio":
        ui_criterios.dialogo_criterio(u.id, historias.obter(u.id, ids[0]))
    elif nome == "novo_epico":
        pagina_epicos.dialogo_epico(u.id, ids[0])
    elif nome == "excluir_epico":
        pagina_epicos.dialogo_exclusao(u.id, next(e for e in epicos.listar(u.id, ids[0]) if e.id == ids[1]))


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


def _tela(usuario, script=_pagina_historias, args=(), estado=None) -> AppTest:
    at = AppTest.from_function(script, args=args, default_timeout=20)
    at.session_state["usuario_autenticado"] = usuario
    for chave, valor in (estado or {}).items():
        at.session_state[chave] = valor
    return at.run()


def _historia(ana, projeto, **kw):
    dados = {"papel": "visitante", "acao": "filtrar a lista de produtos", "beneficio": "achar rápido"}
    dados.update(kw)
    return historias.criar(ana.id, projeto.id, **dados)


def _textos(elementos):
    return [e.value for e in elementos]


# ---------- Q-14: lista ----------

def test_exige_login():
    at = AppTest.from_function(_pagina_historias, default_timeout=20).run()
    assert any("Faça login" in e.value for e in at.error)


def test_lista_mostra_chips_e_pendencias(ctx):
    ana, projeto = ctx
    catalogo = epicos.criar(ana.id, projeto.id, "Catálogo")
    _historia(ana, projeto, story_points=5, moscow="M", epicos_ids=[catalogo.id])
    _historia(ana, projeto, acao="exportar pedidos", story_points=2, moscow="W")
    at = _tela(ana)
    assert not at.exception
    corpo = " ".join(_textos(at.markdown) + _textos(at.caption))
    assert "`Catálogo`" in corpo and "*sem épico*" in corpo  # pendência visível
    assert "5 pts · M · RICE —" in corpo  # sem RICE aparece como traço, nunca como zero


def test_filtros_por_epico_etiqueta_e_pontos(ctx):
    ana, projeto = ctx
    e = epicos.criar(ana.id, projeto.id, "Catálogo")
    _historia(ana, projeto, acao="ver detalhe", story_points=5, moscow="M", epicos_ids=[e.id])
    _historia(ana, projeto, acao="exportar pedidos", story_points=2, moscow="W")
    at = _tela(ana)
    at.selectbox(key="flt_hist_moscow").select("W").run()
    corpo = " ".join(_textos(at.markdown))
    assert "exportar pedidos" in corpo and "ver detalhe" not in corpo
    at.selectbox(key="flt_hist_moscow").select(None).run()
    at.selectbox(key="flt_hist_pontos").select(5).run()
    corpo = " ".join(_textos(at.markdown))
    assert "ver detalhe" in corpo and "exportar pedidos" not in corpo
    at.selectbox(key="flt_hist_epico").select(e.id).select_index(0)  # sem erro ao escolher o épico


def test_projeto_sem_product_backlog_desabilita_nova_historia(engine, ctx):
    ana, _ = ctx
    outro = projetos.criar(ana.id, "Sem backlog")
    at = _tela(ana, estado={"backlogs_projeto_id": outro.id})
    assert at.button(key="btn_nova_historia").disabled
    assert any("product backlog" in i.value for i in at.info)


# ---------- Q-15 / Q-16: nova história ----------

def _preencher(at, papel="visitante", acao="filtrar a lista de produtos", beneficio="achar rápido"):
    at.text_input(key="hfnova_papel").input(papel)
    at.text_input(key="hfnova_acao").input(acao)
    at.text_input(key="hfnova_beneficio").input(beneficio)
    return at.run()


def test_nova_historia_mostra_a_frase_em_tempo_real(ctx):
    ana, projeto = ctx
    at = _tela(ana, _dialogo, ("nova_historia", projeto.id))
    assert any("Como um ______, eu quero ______, para ______." in i.value for i in at.info)
    at = _preencher(at)
    assert any("Como um visitante, eu quero filtrar a lista de produtos, para achar rápido." in i.value for i in at.info)


def test_criar_historia_grava_no_product_backlog_e_avisa(ctx):
    ana, projeto = ctx
    e = epicos.criar(ana.id, projeto.id, "Catálogo")
    at = _tela(ana, _dialogo, ("nova_historia", projeto.id))
    at = _preencher(at)
    at.selectbox(key="hfnova_pontos").select(5)
    at.selectbox(key="hfnova_moscow").select("M")
    at.multiselect(key="hfnova_epicos").select(e.id)
    at.button(key="hfnova_salvar").click().run()
    assert not at.exception
    h = historias.listar(ana.id, projeto.id)[0]
    assert (h.codigo, h.story_points, h.moscow, [x.nome for x in h.epicos]) == ("SGR-1", 5, "M", ["Catálogo"])
    assert at.session_state["aviso_historia"] == "✓ História criada."


def test_campo_vazio_mostra_o_erro_no_campo_e_nao_apaga_o_que_foi_digitado(ctx):
    ana, projeto = ctx
    at = _tela(ana, _dialogo, ("nova_historia", projeto.id))
    at = _preencher(at, acao="")
    at.button(key="hfnova_salvar").click().run()
    assert any("Informe a ação" in e.value for e in at.error)
    assert at.text_input(key="hfnova_papel").value == "visitante"
    assert historias.listar(ana.id, projeto.id) == []


def test_salvar_e_adicionar_criterios_abre_a_historia_e_encadeia_o_criterio(ctx):
    ana, projeto = ctx
    at = _tela(ana, _dialogo, ("nova_historia", projeto.id))
    at = _preencher(at)
    at.button(key="hfnova_criterios").click().run()
    h = historias.listar(ana.id, projeto.id)[0]
    assert at.session_state["historia_aberta"] == h.id
    assert at.session_state["criterio_reabrir"] == h.id
    # na página, a história aberta reabre o diálogo de critério
    at = _tela(ana, estado={"historia_aberta": h.id, "criterio_reabrir": h.id})
    assert at.button(key=f"nc{h.id}_salvar").label == "Salvar critério"


def test_editar_historia_atualiza_os_campos(ctx):
    ana, projeto = ctx
    h = _historia(ana, projeto)
    at = _tela(ana, _dialogo, ("editar_historia", projeto.id, h.id))
    at.text_input(key=f"hf{h.id}_acao").input("comparar produtos")
    at.selectbox(key=f"hf{h.id}_pontos").select(8)
    at.button(key=f"hf{h.id}_salvar").click().run()
    novo = historias.obter(ana.id, h.id)
    assert (novo.acao, novo.story_points) == ("comparar produtos", 8)
    assert at.session_state["aviso_historia"] == "✓ História atualizada."


# ---------- Q-18: detalhe ----------

def test_detalhe_mostra_os_atributos_de_priorizacao_e_os_criterios(ctx):
    ana, projeto = ctx
    e = epicos.criar(ana.id, projeto.id, "Catálogo")
    h = _historia(ana, projeto, story_points=5, moscow="M", epicos_ids=[e.id])
    criterios.criar(ana.id, h.id, "que estou na página de produtos", "seleciono Eletrônicos", "vejo só eletrônicos")
    at = _tela(ana, estado={"historia_aberta": h.id})
    assert not at.exception
    metricas = {m.label: m.value for m in at.metric}
    assert metricas == {"Pontos": "5", "MoSCoW": "M", "RICE": "—", "Épicos": "1"}
    corpo = " ".join(_textos(at.markdown))
    assert "SGR-1" in " ".join(t.value for t in at.title) and "Critérios de aceitação (1)" in corpo
    assert "Dado que estou na página de produtos, quando seleciono Eletrônicos, então vejo só eletrônicos." in corpo


def test_historia_inexistente_volta_para_a_lista(ctx):
    ana, _ = ctx
    at = _tela(ana, estado={"historia_aberta": 9999})
    assert not at.exception and "historia_aberta" not in at.session_state


# ---------- Q-19 / Q-20: critérios ----------

def test_novo_criterio_mostra_a_frase_e_salva(ctx):
    ana, projeto = ctx
    h = _historia(ana, projeto)
    at = _tela(ana, _dialogo, ("novo_criterio", h.id))
    at.text_input(key=f"nc{h.id}_contexto").input("que estou na página de produtos")
    at.text_input(key=f"nc{h.id}_acao").input("seleciono Eletrônicos")
    at = at.text_input(key=f"nc{h.id}_resultado").input("vejo só eletrônicos").run()
    assert any("Dado que estou na página de produtos, quando seleciono Eletrônicos, então vejo só eletrônicos." in i.value
               for i in at.info)
    at.button(key=f"nc{h.id}_salvar").click().run()
    assert [c.acao for c in criterios.listar(ana.id, h.id)] == ["seleciono Eletrônicos"]
    assert at.session_state["aviso_historia"] == "✓ Critério salvo."
    assert "criterio_reabrir" not in at.session_state


def test_salvar_e_adicionar_outro_pede_para_reabrir_o_dialogo(ctx):
    ana, projeto = ctx
    h = _historia(ana, projeto)
    at = _tela(ana, _dialogo, ("novo_criterio", h.id))
    at.text_input(key=f"nc{h.id}_contexto").input("que há filtros")
    at.text_input(key=f"nc{h.id}_acao").input("limpo os filtros")
    at.text_input(key=f"nc{h.id}_resultado").input("vejo tudo")
    at.button(key=f"nc{h.id}_outro").click().run()
    assert at.session_state["criterio_reabrir"] == h.id


def test_criterio_incompleto_mostra_erro_por_campo(ctx):
    ana, projeto = ctx
    h = _historia(ana, projeto)
    at = _tela(ana, _dialogo, ("novo_criterio", h.id))
    at.text_input(key=f"nc{h.id}_contexto").input("que há filtros")
    at.button(key=f"nc{h.id}_salvar").click().run()
    erros = " ".join(_textos(at.error))
    assert "Informe a ação" in erros and "Informe o resultado" in erros and "Informe o contexto" not in erros
    assert criterios.listar(ana.id, h.id) == []


def test_editar_criterio_no_lugar(ctx):
    ana, projeto = ctx
    h = _historia(ana, projeto)
    c = criterios.criar(ana.id, h.id, "que há filtros", "limpo os filtros", "vejo tudo")
    at = _tela(ana, estado={"historia_aberta": h.id})
    at.button(key=f"btn_editar_criterio_{c.id}").click().run()
    at.text_input(key=f"ec{c.id}_resultado").input("a lista volta ao normal")
    at.button(key=f"ec{c.id}_salvar").click().run()
    assert criterios.listar(ana.id, h.id)[0].resultado == "a lista volta ao normal"
    assert _textos(at.toast) == ["✓ Critério atualizado."]  # a página reexecuta e mostra o aviso


def test_editar_criterio_invalido_mostra_o_erro_e_nao_grava(ctx):
    ana, projeto = ctx
    h = _historia(ana, projeto)
    c = criterios.criar(ana.id, h.id, "que há filtros", "limpo os filtros", "vejo tudo")
    at = _tela(ana, estado={"historia_aberta": h.id})
    at.button(key=f"btn_editar_criterio_{c.id}").click().run()
    at.text_input(key=f"ec{c.id}_acao").input("")
    at.button(key=f"ec{c.id}_salvar").click().run()
    assert any("Informe a ação" in e.value for e in at.error)
    assert criterios.listar(ana.id, h.id)[0].acao == "limpo os filtros"


def test_cancelar_edicao_nao_altera(ctx):
    ana, projeto = ctx
    h = _historia(ana, projeto)
    c = criterios.criar(ana.id, h.id, "que há filtros", "limpo os filtros", "vejo tudo")
    at = _tela(ana, estado={"historia_aberta": h.id})
    at.button(key=f"btn_editar_criterio_{c.id}").click().run()
    at.button(key=f"ec{c.id}_cancelar").click().run()
    assert not any(k.startswith("ec") for k in [b.key for b in at.button])


# ---------- Q-21: épicos da história ----------

def test_vincular_epicos_substitui_o_conjunto(ctx):
    ana, projeto = ctx
    a = epicos.criar(ana.id, projeto.id, "Catálogo")
    b = epicos.criar(ana.id, projeto.id, "Checkout")
    h = _historia(ana, projeto, epicos_ids=[a.id])
    at = _tela(ana, _dialogo, ("vincular", h.id))
    at.multiselect(key=f"ve{h.id}_epicos").unselect(a.id).select(b.id)
    at.button(key=f"ve{h.id}_vincular").click().run()
    assert [e.nome for e in historias.obter(ana.id, h.id).epicos] == ["Checkout"]
    assert at.session_state["aviso_historia"] == "✓ Épicos atualizados."


def test_vincular_sem_epicos_no_projeto_orienta_a_criar(ctx):
    ana, projeto = ctx
    h = _historia(ana, projeto)
    at = _tela(ana, _dialogo, ("vincular", h.id))
    assert any("ainda não tem épicos" in i.value for i in at.info)


# ---------- Q-22: exclusão ----------

def test_excluir_historia_exige_o_reconhecimento_e_mostra_o_inventario(ctx):
    ana, projeto = ctx
    e = epicos.criar(ana.id, projeto.id, "Catálogo")
    h = _historia(ana, projeto, story_points=5, moscow="M", epicos_ids=[e.id])
    criterios.criar(ana.id, h.id, "que a", "faço b", "vejo c")
    criterios.criar(ana.id, h.id, "que d", "faço e", "vejo f")
    at = _tela(ana, _dialogo, ("excluir_historia", h.id))
    corpo = " ".join(_textos(at.markdown))
    assert "2 critérios de aceitação" in corpo and "vínculo com 1 épico" in corpo
    assert "estimativa de 5 pontos, etiqueta M" in corpo
    assert at.button(key=f"hx{h.id}_excluir").disabled
    at.checkbox(key=f"hx{h.id}_ciente").check().run()
    assert not at.button(key=f"hx{h.id}_excluir").disabled
    at.button(key=f"hx{h.id}_excluir").click().run()
    assert historias.listar(ana.id, projeto.id) == []
    assert at.session_state["aviso_historia"] == "✓ História excluída."
    assert epicos.listar(ana.id, projeto.id)[0].historias == 0  # a contagem do épico acompanha


def test_cancelar_exclusao_mantem_a_historia(ctx):
    ana, projeto = ctx
    h = _historia(ana, projeto)
    at = _tela(ana, _dialogo, ("excluir_historia", h.id))
    at.button(key=f"hx{h.id}_cancelar").click().run()
    assert len(historias.listar(ana.id, projeto.id)) == 1


# ---------- épicos ----------

def test_pagina_de_epicos_lista_com_historias_e_pontos(ctx):
    ana, projeto = ctx
    e = epicos.criar(ana.id, projeto.id, "Catálogo", "Navegação de produtos")
    _historia(ana, projeto, story_points=5, epicos_ids=[e.id])
    at = _tela(ana, _pagina_epicos)
    assert not at.exception
    corpo = " ".join(_textos(at.markdown) + _textos(at.caption))
    assert "Catálogo" in corpo and "1 história · 5 pontos" in corpo


def test_criar_epico_e_nome_repetido(ctx):
    ana, projeto = ctx
    at = _tela(ana, _dialogo, ("novo_epico", projeto.id))
    at.text_input(key="epnovo_nome").input("Catálogo")
    at.button(key="epnovo_salvar").click().run()
    assert [e.nome for e in epicos.listar(ana.id, projeto.id)] == ["Catálogo"]
    assert at.session_state["aviso_epico"] == "✓ Épico criado."
    at = _tela(ana, _dialogo, ("novo_epico", projeto.id))
    at.text_input(key="epnovo_nome").input("catálogo")
    at.button(key="epnovo_salvar").click().run()
    assert any("Já existe um épico" in e.value for e in at.error)
    assert at.text_input(key="epnovo_nome").value == "catálogo"


def test_epico_com_historias_nao_pode_ser_excluido(ctx):
    ana, projeto = ctx
    e = epicos.criar(ana.id, projeto.id, "Catálogo")
    h = _historia(ana, projeto, epicos_ids=[e.id])
    at = _tela(ana, _dialogo, ("excluir_epico", projeto.id, e.id))
    assert any("ainda está ligada" in w.value for w in at.warning)
    assert at.button(key=f"epx{e.id}_excluir").disabled
    historias.desvincular_epico(ana.id, h.id, e.id)
    at = _tela(ana, _dialogo, ("excluir_epico", projeto.id, e.id))
    at.button(key=f"epx{e.id}_excluir").click().run()
    assert epicos.listar(ana.id, projeto.id) == []
    assert at.session_state["aviso_epico"] == "✓ Épico excluído."
