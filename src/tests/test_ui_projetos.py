"""Fluxo de tela do CRUD de projetos (Storyboard 1 / requisito 4)."""
import pytest
from sqlalchemy import text
from streamlit.testing.v1 import AppTest

from sgr.db import session as db_session
from sgr.services import autenticacao, projetos


def _script():
    from sgr.ui.pagina_projetos import pagina_projetos

    pagina_projetos()


@pytest.fixture()
def ana(engine, test_url, monkeypatch):
    """Usuária Ana gravada no banco de testes (commits reais, tabelas limpas antes e depois)."""
    monkeypatch.setenv("DATABASE_URL", test_url)
    db_session.get_engine.cache_clear()
    db_session._session_factory.cache_clear()
    monkeypatch.setattr(autenticacao, "_rounds", 4)

    def limpar():
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE usuario RESTART IDENTITY CASCADE"))
            conn.execute(text("TRUNCATE registro_auditoria"))

    limpar()
    yield autenticacao.cadastrar("Ana", "ana@x.com", "senha-segura-123", "senha-segura-123")
    limpar()
    db_session.get_engine.cache_clear()
    db_session._session_factory.cache_clear()


def _dialogo_formulario(projeto_id=None):
    """Abre o diálogo de criar/editar diretamente.

    O AppTest reexecuta o script inteiro a cada interação (o Streamlit real reexecuta só o
    fragmento do diálogo); por isso os diálogos são testados chamando-os em todo run.
    """
    from sgr.services import projetos
    from sgr.ui import pagina_projetos as pp
    from sgr.ui.sessao import usuario_logado

    u = usuario_logado()
    projeto = projetos.obter(u.id, projeto_id) if projeto_id else None
    pp._dialogo_formulario(u.id, projeto)


def _dialogo_exclusao(projeto_id):
    from sgr.services import projetos
    from sgr.services.projeto_service import ProjetoNaoEncontrado
    from sgr.ui import pagina_projetos as pp
    from sgr.ui.sessao import usuario_logado

    u = usuario_logado()
    try:
        pp._dialogo_exclusao(u.id, projetos.obter(u.id, projeto_id))
    except ProjetoNaoEncontrado:
        pass  # já excluído: depois do st.rerun() o script roda de novo


def _tela(usuario, script=_script, args=()) -> AppTest:
    at = AppTest.from_function(script, args=args, default_timeout=20)
    at.session_state["usuario_autenticado"] = usuario
    return at.run()


def _titulos(at):
    return [b.label for b in at.button if b.key.startswith("abrir_")]


def _aviso(at):
    return at.session_state["aviso_projeto"]


def test_exige_login():
    at = AppTest.from_function(_script, default_timeout=20).run()
    assert any("Faça login" in e.value for e in at.error)


# ---------- lista ----------

def test_lista_vazia(ana):
    at = _tela(ana)
    assert not at.exception
    assert any("Você ainda não tem projetos" in s.value for s in at.subheader)
    assert at.button(key="btn_primeiro_projeto").label == "Criar meu primeiro projeto"


def test_lista_mostra_resumo_e_aviso_de_sucesso(ana, engine):
    p = projetos.criar(ana.id, "Portal do Cliente")
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO backlog (projeto_id, tipo, nome) VALUES (:p,'PRODUCT','PB')"), {"p": p.id})
    at = AppTest.from_function(_script, default_timeout=20)
    at.session_state["usuario_autenticado"] = ana
    at.session_state["aviso_projeto"] = "Projeto criado."
    at.run()
    assert _titulos(at) == ["Portal do Cliente"]
    assert any("1 backlog · 0 história" in c.value for c in at.caption)
    assert at.toast[0].value == "Projeto criado."
    assert "aviso_projeto" not in at.session_state  # o aviso aparece uma vez só


def test_busca_e_filtros(ana):
    projetos.criar(ana.id, "Portal do Cliente")
    projetos.criar(ana.id, "App de Campo")
    at = _tela(ana)
    assert _titulos(at) == ["App de Campo", "Portal do Cliente"]
    at.text_input(key="busca_projetos").input("portal")
    at = at.run()
    assert _titulos(at) == ["Portal do Cliente"]
    at.text_input(key="busca_projetos").input("zzz")
    at = at.run()
    assert _titulos(at) == [] and any("Nenhum projeto encontrado" in i.value for i in at.info)
    at.text_input(key="busca_projetos").input("")
    at.radio(key="filtro_projetos").set_value("Arquivados")
    at = at.run()
    assert _titulos(at) == [] and any("Nenhum projeto encontrado" in i.value for i in at.info)


def test_membro_ve_o_projeto_mas_nao_edita_nem_exclui(ana, engine):
    outro = autenticacao.cadastrar("Beto", "beto@x.com", "senha-segura-123", "senha-segura-123")
    p = projetos.criar(outro.id, "Do Beto")
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO projeto_membro (projeto_id, usuario_id) VALUES (:p,:u)"), {"p": p.id, "u": ana.id})
    at = _tela(ana)
    assert _titulos(at) == ["Do Beto"]
    assert not [b for b in at.button if b.key.startswith(("editar_", "excluir_"))]
    at.button(key=f"abrir_{p.id}").click()
    at = at.run()
    assert at.title[0].value == "Do Beto"
    assert not [b for b in at.button if b.key in ("btn_editar_projeto", "btn_excluir_projeto")]


# ---------- detalhe ----------

def test_ver_projeto_mostra_painel_e_volta_para_a_lista(ana):
    p = projetos.criar(ana.id, "Portal", "Área do cliente")
    at = _tela(ana)
    at.button(key=f"abrir_{p.id}").click()
    at = at.run()
    assert at.title[0].value == "Portal"
    assert any("Área do cliente" in m.value for m in at.markdown)
    assert [m.label for m in at.metric] == ["Product backlog", "Sprint backlogs", "Épicos", "Histórias", "Story points"]
    at.button(key="btn_voltar_projetos").click()
    at = at.run()
    assert at.title[0].value == "Projetos"


def test_projeto_aberto_que_deixou_de_existir_volta_para_a_lista(ana):
    at = AppTest.from_function(_script, default_timeout=20)
    at.session_state["usuario_autenticado"] = ana
    at.session_state["projeto_aberto"] = 424242
    at.run()
    assert not at.exception and at.title[0].value == "Projetos"


# ---------- diálogos ----------

def test_dialogo_criar_projeto(ana):
    at = _tela(ana, _dialogo_formulario)
    at.text_input(key="projeto_nome_novo").input("Portal do Cliente")
    at.text_area(key="projeto_descricao_novo").input("Autosserviço")
    at.button(key="btn_salvar_projeto_novo").click()
    at = at.run()
    assert not at.exception
    (p,) = projetos.listar(ana.id)
    assert (p.nome, p.descricao) == ("Portal do Cliente", "Autosserviço")
    assert _aviso(at) == "Projeto criado."


def test_dialogo_criar_com_erro_mantem_os_dados_digitados(ana):
    at = _tela(ana, _dialogo_formulario)
    at.text_input(key="projeto_nome_novo").input("   ")
    at.text_area(key="projeto_descricao_novo").input("Integração com o ERP fiscal")
    at.button(key="btn_salvar_projeto_novo").click()
    at = at.run()
    assert any("Informe o nome do projeto." in e.value for e in at.error)
    assert at.text_area(key="projeto_descricao_novo").value == "Integração com o ERP fiscal"
    assert projetos.listar(ana.id) == []
    assert "aviso_projeto" not in at.session_state


def test_dialogo_criar_nome_repetido_mostra_erro(ana):
    projetos.criar(ana.id, "Portal")
    at = _tela(ana, _dialogo_formulario)
    at.text_input(key="projeto_nome_novo").input("portal")
    at.button(key="btn_salvar_projeto_novo").click()
    at = at.run()
    assert any("já tem um projeto com este nome" in e.value for e in at.error)
    assert len(projetos.listar(ana.id)) == 1


def test_dialogo_editar_vem_preenchido_e_salva(ana):
    p = projetos.criar(ana.id, "Velho", "d")
    at = _tela(ana, _dialogo_formulario, (p.id,))
    assert at.text_input(key=f"projeto_nome_{p.id}").value == "Velho"
    assert at.text_area(key=f"projeto_descricao_{p.id}").value == "d"
    assert any("não afeta backlogs" in c.value for c in at.caption)
    at.text_input(key=f"projeto_nome_{p.id}").input("Novo")
    at.button(key=f"btn_salvar_projeto_{p.id}").click()
    at = at.run()
    assert not at.exception
    novo = projetos.obter(ana.id, p.id)
    assert (novo.nome, novo.descricao) == ("Novo", "d")
    assert _aviso(at) == "Alterações salvas."


def test_dialogo_excluir_exige_reconhecimento_e_remove(ana):
    p = projetos.criar(ana.id, "Portal")
    projetos.criar(ana.id, "Outro")
    at = _tela(ana, _dialogo_exclusao, (p.id,))
    assert any("Esta ação removerá permanentemente" in m.value for m in at.markdown)
    assert at.button(key=f"btn_confirmar_exclusao_{p.id}").disabled
    at.checkbox(key=f"chk_excluir_{p.id}").check().run()
    assert not at.button(key=f"btn_confirmar_exclusao_{p.id}").disabled
    at.button(key=f"btn_confirmar_exclusao_{p.id}").click()
    at = at.run()
    assert not at.exception
    assert [x.nome for x in projetos.listar(ana.id)] == ["Outro"]
    assert _aviso(at) == "Projeto excluído."


def test_dialogo_excluir_cancelar_nao_remove(ana):
    p = projetos.criar(ana.id, "Portal")
    at = _tela(ana, _dialogo_exclusao, (p.id,))
    at.button(key=f"btn_cancelar_exclusao_{p.id}").click()
    at.run()
    assert len(projetos.listar(ana.id)) == 1
