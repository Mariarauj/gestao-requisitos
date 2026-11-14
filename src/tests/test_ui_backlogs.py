"""Fluxo de tela do CRUD de backlogs (Storyboard 3 / requisitos 5 e 6)."""
from datetime import date

import pytest
from sqlalchemy import text
from streamlit.testing.v1 import AppTest

from sgr.db import session as db_session
from sgr.services import autenticacao, backlogs, projetos


def _script():
    from sgr.ui.pagina_backlogs import pagina_backlogs

    pagina_backlogs()


def _dialogo_product(backlog_id=None):
    """Abre o diálogo diretamente: o AppTest reexecuta o script inteiro a cada interação
    (o Streamlit real reexecuta só o fragmento do diálogo), então chamamos o diálogo em todo run."""
    from sgr.services import backlogs, projetos
    from sgr.ui import pagina_backlogs as pb
    from sgr.ui.sessao import usuario_logado

    u = usuario_logado()
    projeto = projetos.listar(u.id)[0]
    atual = backlogs.obter(u.id, backlog_id) if backlog_id else None
    existente = backlogs.listar(u.id, projeto.id).product
    pb._dialogo_product(u.id, projeto.id, projeto.nome, atual, existente)


def _dialogo_sprint(backlog_id=None):
    from sgr.services import backlogs, projetos
    from sgr.ui import pagina_backlogs as pb
    from sgr.ui.sessao import usuario_logado

    u = usuario_logado()
    projeto = projetos.listar(u.id)[0]
    atual = backlogs.obter(u.id, backlog_id) if backlog_id else None
    pb._dialogo_sprint(u.id, projeto.id, projeto.nome, atual)


def _dialogo_exclusao(backlog_id):
    from sgr.services import backlogs
    from sgr.services.backlog_service import BacklogNaoEncontrado
    from sgr.ui import pagina_backlogs as pb
    from sgr.ui.sessao import usuario_logado

    u = usuario_logado()
    try:
        b = backlogs.obter(u.id, backlog_id)
    except BacklogNaoEncontrado:
        return  # já excluído: depois do st.rerun() o script roda de novo
    tem_product = backlogs.listar(u.id, b.projeto_id).product is not None
    pb._dialogo_exclusao(u.id, b, tem_product)


@pytest.fixture()
def ctx(engine, test_url, monkeypatch):
    """Ana com um projeto, gravados no banco de testes (commits reais, tabelas limpas antes e depois)."""
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
    yield ana, projeto
    limpar()
    db_session.get_engine.cache_clear()
    db_session._session_factory.cache_clear()


def _tela(usuario, script=_script, args=()) -> AppTest:
    at = AppTest.from_function(script, args=args, default_timeout=20)
    at.session_state["usuario_autenticado"] = usuario
    return at.run()


def _abrir(at):
    return [b.label for b in at.button if b.key.startswith("abrir_backlog_")]


def _aviso(at):
    return at.session_state["aviso_backlog"]


def _historia(engine, projeto_id, backlog_id, codigo, pts=3):
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO historia (projeto_id, backlog_id, codigo, papel, acao, beneficio, moscow, story_points) "
            "VALUES (:p,:b,:c,'gerente','agir','ganhar','M',:s)"), {"p": projeto_id, "b": backlog_id, "c": codigo, "s": pts})


def test_exige_login():
    at = AppTest.from_function(_script, default_timeout=20).run()
    assert any("Faça login" in e.value for e in at.error)


def test_sem_projetos_orienta_a_criar_um(engine, test_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", test_url)
    db_session.get_engine.cache_clear()
    db_session._session_factory.cache_clear()
    monkeypatch.setattr(autenticacao, "_rounds", 4)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE usuario RESTART IDENTITY CASCADE"))
    ana = autenticacao.cadastrar("Ana", "ana@x.com", "senha-segura-123", "senha-segura-123")
    at = _tela(ana)
    assert any("Crie um projeto" in i.value for i in at.info)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE usuario RESTART IDENTITY CASCADE"))


# ---------- lista ----------

def test_projeto_sem_backlogs_mostra_estado_vazio_do_product(ctx):
    at = _tela(ctx[0])
    assert not at.exception
    assert any("Este projeto ainda não tem product backlog" in m.value for m in at.markdown)
    assert at.button(key="btn_criar_product_vazio").label == "Criar product backlog"
    assert not at.button(key="btn_novo_product").disabled
    assert _abrir(at) == []


def test_lista_com_product_e_sprints(ctx, engine):
    ana, proj = ctx
    pb = backlogs.criar_product(ana.id, proj.id, "Product Backlog", "Tudo do produto")
    s12 = backlogs.criar_sprint(ana.id, proj.id, "Sprint 12", date(2026, 10, 1), date(2026, 10, 14))
    backlogs.criar_sprint(ana.id, proj.id, "Sprint 13", date(2026, 10, 15), date(2026, 10, 28))
    _historia(engine, proj.id, pb.id, "H-1", 5)
    _historia(engine, proj.id, s12.id, "H-2", 3)
    at = _tela(ana)
    assert _abrir(at) == ["Product Backlog", "Sprint 13", "Sprint 12"]  # sprints do mais recente ao mais antigo
    legendas = [c.value for c in at.caption]
    assert "1 história · 5 pontos" in legendas
    assert "01/10/2026 a 14/10/2026 · Planejado" in legendas
    assert any(s.value == "Sprint backlogs 2" for s in at.subheader)


def test_segundo_product_backlog_fica_bloqueado_com_explicacao(ctx):
    ana, proj = ctx
    backlogs.criar_product(ana.id, proj.id, "PB")
    at = _tela(ana)
    assert at.button(key="btn_novo_product").disabled
    assert at.button(key="btn_novo_product").help == "Este projeto já tem um product backlog. Para outro, crie um novo projeto."
    assert any("Para outro, crie um novo projeto" in c.value for c in at.caption)


def test_selecao_de_projeto_isola_os_backlogs(ctx):
    ana, proj = ctx
    outro = projetos.criar(ana.id, "App de Campo")
    backlogs.criar_product(ana.id, proj.id, "PB do Portal")
    backlogs.criar_product(ana.id, outro.id, "PB do App")
    at = _tela(ana)  # ordem alfabética: App de Campo primeiro
    assert at.selectbox(key="seletor_projeto_backlogs").value == outro.id
    assert _abrir(at) == ["PB do App"]
    at.selectbox(key="seletor_projeto_backlogs").set_value(proj.id)
    at = at.run()
    assert _abrir(at) == ["PB do Portal"]


def test_projeto_aberto_na_pagina_de_projetos_vem_selecionado(ctx):
    ana, proj = ctx
    projetos.criar(ana.id, "App de Campo")
    at = AppTest.from_function(_script, default_timeout=20)
    at.session_state["usuario_autenticado"] = ana
    at.session_state["projeto_aberto"] = proj.id
    at.run()
    assert at.selectbox(key="seletor_projeto_backlogs").value == proj.id


# ---------- detalhe ----------

def test_ver_backlog_mostra_historias_e_volta(ctx, engine):
    ana, proj = ctx
    pb = backlogs.criar_product(ana.id, proj.id, "PB", "Tudo")
    _historia(engine, proj.id, pb.id, "SGR-1", 5)
    at = _tela(ana)
    at.button(key=f"abrir_backlog_{pb.id}").click()
    at = at.run()
    assert at.title[1].value == "PB"
    assert [(m.label, m.value) for m in at.metric] == [("Histórias", "1"), ("Story points", "5")]
    assert any("SGR-1" in m.value for m in at.markdown)
    at.button(key="btn_voltar_backlogs").click()
    at = at.run()
    assert _abrir(at) == ["PB"]


def test_detalhe_de_sprint_mostra_periodo_e_duracao(ctx):
    ana, proj = ctx
    s = backlogs.criar_sprint(ana.id, proj.id, "Sprint 13", date(2026, 10, 15), date(2026, 10, 28))
    at = _tela(ana)
    at.button(key=f"abrir_backlog_{s.id}").click()
    at = at.run()
    assert any("15/10/2026 a 28/10/2026 (14 dias) · Planejado" in c.value for c in at.caption)
    assert any("Nenhuma história neste backlog" in c.value for c in at.caption)


def test_backlog_aberto_que_deixou_de_existir_volta_para_a_lista(ctx):
    at = AppTest.from_function(_script, default_timeout=20)
    at.session_state["usuario_autenticado"] = ctx[0]
    at.session_state["backlog_aberto"] = 424242
    at.run()
    assert not at.exception and at.title[0].value == "Backlogs"


# ---------- diálogos: product backlog ----------

def test_dialogo_criar_product_vem_com_sugestao_e_grava(ctx):
    ana, proj = ctx
    at = _tela(ana, _dialogo_product)
    assert at.text_input(key="product_nome_novo").value == "Product Backlog"
    assert any("único product backlog" in i.value for i in at.info)
    at.text_area(key="product_descricao_novo").input("O que reúne")
    at.button(key="btn_salvar_product_novo").click()
    at = at.run()
    assert not at.exception
    pb = backlogs.listar(ana.id, proj.id).product
    assert (pb.nome, pb.descricao) == ("Product Backlog", "O que reúne")
    assert _aviso(at) == "Product backlog criado."


def test_dialogo_criar_product_com_nome_vazio_mostra_erro_no_campo(ctx):
    ana, proj = ctx
    at = _tela(ana, _dialogo_product)
    at.text_input(key="product_nome_novo").input("  ")
    at.text_area(key="product_descricao_novo").input("mantida")
    at.button(key="btn_salvar_product_novo").click()
    at = at.run()
    assert any("Informe o nome do backlog." in e.value for e in at.error)
    assert at.text_area(key="product_descricao_novo").value == "mantida"
    assert backlogs.listar(ana.id, proj.id).product is None


def test_dialogo_do_segundo_product_mostra_aviso_em_vez_do_formulario(ctx):
    ana, proj = ctx
    backlogs.criar_product(ana.id, proj.id, "Product Backlog")
    at = _tela(ana, _dialogo_product)
    assert any("Cada projeto admite apenas um" in e.value for e in at.error)
    assert any("crie um novo projeto" in c.value for c in at.caption)
    assert at.button(key="btn_voltar_aos_backlogs").label == "Voltar aos backlogs"
    assert not at.text_input  # não há formulário


def test_dialogo_editar_product(ctx):
    ana, proj = ctx
    pb = backlogs.criar_product(ana.id, proj.id, "PB", "d")
    at = _tela(ana, _dialogo_product, (pb.id,))
    assert at.text_input(key=f"product_nome_{pb.id}").value == "PB"
    at.text_input(key=f"product_nome_{pb.id}").input("Principal")
    at.button(key=f"btn_salvar_product_{pb.id}").click()
    at = at.run()
    assert backlogs.obter(ana.id, pb.id).nome == "Principal"
    assert _aviso(at) == "Product backlog atualizado."


# ---------- diálogos: sprint ----------

def test_dialogo_criar_sprint_calcula_duracao_e_grava(ctx):
    ana, proj = ctx
    at = _tela(ana, _dialogo_sprint)
    assert at.text_input(key="sprint_nome_novo").value == "Sprint 1"
    at.date_input(key="sprint_inicio_novo").set_value(date(2026, 10, 15))
    at.date_input(key="sprint_fim_novo").set_value(date(2026, 10, 28))
    at.text_area(key="sprint_meta_novo").input("Entregar o login")
    at = at.run()
    assert any(c.value == "Duração: 14 dias" for c in at.caption)
    at.button(key="btn_salvar_sprint_novo").click()
    at = at.run()
    assert not at.exception
    (s,) = backlogs.listar(ana.id, proj.id).sprints
    assert (s.nome, s.data_inicio, s.data_fim, s.descricao, s.estado) == ("Sprint 1", date(2026, 10, 15), date(2026, 10, 28), "Entregar o login", "PLANEJADO")
    assert _aviso(at) == "Sprint criado."


def test_dialogo_criar_sprint_com_fim_antes_do_inicio_mostra_erro_no_campo(ctx):
    ana, proj = ctx
    at = _tela(ana, _dialogo_sprint)
    at.date_input(key="sprint_inicio_novo").set_value(date(2026, 10, 15))
    at.date_input(key="sprint_fim_novo").set_value(date(2026, 10, 14))
    at = at.run()
    assert not any("Duração" in c.value for c in at.caption)
    at.button(key="btn_salvar_sprint_novo").click()
    at = at.run()
    assert any("A data de fim deve ser posterior à data de início." in e.value for e in at.error)
    assert backlogs.listar(ana.id, proj.id).sprints == []


def test_dialogo_editar_sprint_mostra_estado_somente_leitura(ctx):
    ana, proj = ctx
    s = backlogs.criar_sprint(ana.id, proj.id, "Sprint 13", date(2026, 10, 15), date(2026, 10, 28), "Meta")
    at = _tela(ana, _dialogo_sprint, (s.id,))
    assert at.date_input(key=f"sprint_inicio_{s.id}").value == date(2026, 10, 15)
    estado = at.text_input(key=f"sprint_estado_{s.id}")
    assert estado.value == "Planejado" and estado.disabled
    assert any("não são afetadas" in i.value for i in at.info)
    at.text_input(key=f"sprint_nome_{s.id}").input("Sprint 13B")
    at.button(key=f"btn_salvar_sprint_{s.id}").click()
    at = at.run()
    assert backlogs.obter(ana.id, s.id).nome == "Sprint 13B"
    assert _aviso(at) == "Sprint atualizado."


# ---------- diálogos: exclusão ----------

def test_excluir_sprint_com_historias_exige_reconhecimento_e_devolve_ao_product(ctx, engine):
    ana, proj = ctx
    pb = backlogs.criar_product(ana.id, proj.id, "PB")
    s = backlogs.criar_sprint(ana.id, proj.id, "Sprint 13", date(2026, 10, 15), date(2026, 10, 28))
    _historia(engine, proj.id, s.id, "H-1")
    _historia(engine, proj.id, s.id, "H-2")
    at = _tela(ana, _dialogo_exclusao, (s.id,))
    assert any("2 histórias serão movidas de volta ao Product Backlog" in m.value for m in at.markdown)
    assert at.button(key=f"btn_confirmar_exclusao_{s.id}").disabled
    at.checkbox(key=f"chk_excluir_{s.id}").check().run()
    at.button(key=f"btn_confirmar_exclusao_{s.id}").click()
    at = at.run()
    assert not at.exception
    r = backlogs.listar(ana.id, proj.id)
    assert r.sprints == [] and r.product.historias == 2
    assert _aviso(at) == "Sprint excluído."


def test_excluir_sprint_vazio_nao_pede_reconhecimento(ctx):
    ana, proj = ctx
    s = backlogs.criar_sprint(ana.id, proj.id, "S", date(2026, 1, 1), date(2026, 1, 14))
    at = _tela(ana, _dialogo_exclusao, (s.id,))
    assert not at.checkbox
    at.button(key=f"btn_confirmar_exclusao_{s.id}").click()
    at.run()
    assert backlogs.listar(ana.id, proj.id).sprints == []


def test_excluir_product_com_historias_e_bloqueado(ctx, engine):
    ana, proj = ctx
    pb = backlogs.criar_product(ana.id, proj.id, "PB")
    _historia(engine, proj.id, pb.id, "H-1")
    at = _tela(ana, _dialogo_exclusao, (pb.id,))
    assert any("Não é possível excluir o Product Backlog." in e.value for e in at.error)
    assert any("1 história depende dele" in m.value for m in at.markdown)
    assert not [b for b in at.button if b.key.startswith("btn_confirmar_exclusao")]
    assert at.button(key=f"btn_entendi_{pb.id}").label == "Entendi"
    assert backlogs.listar(ana.id, proj.id).product is not None


def test_excluir_product_vazio(ctx):
    ana, proj = ctx
    pb = backlogs.criar_product(ana.id, proj.id, "PB")
    at = _tela(ana, _dialogo_exclusao, (pb.id,))
    assert any("não tem histórias e pode ser excluído" in m.value for m in at.markdown)
    at.button(key=f"btn_confirmar_exclusao_{pb.id}").click()
    at = at.run()
    assert backlogs.listar(ana.id, proj.id).product is None
    assert _aviso(at) == "Product backlog excluído."


def test_cancelar_exclusao_nao_remove(ctx):
    ana, proj = ctx
    s = backlogs.criar_sprint(ana.id, proj.id, "S", date(2026, 1, 1), date(2026, 1, 14))
    at = _tela(ana, _dialogo_exclusao, (s.id,))
    at.button(key=f"btn_cancelar_exclusao_{s.id}").click()
    at.run()
    assert len(backlogs.listar(ana.id, proj.id).sprints) == 1
