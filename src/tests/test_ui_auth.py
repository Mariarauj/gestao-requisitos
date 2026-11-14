"""Fluxo de tela: serviços só acessíveis após autenticação (requisito 3)."""
from pathlib import Path

import pytest
from sqlalchemy import text
from streamlit.testing.v1 import AppTest

from sgr.db import session as db_session
from sgr.services import autenticacao
from sgr.services.limitador import LimitadorTentativas

APP = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture()
def app(engine, test_url, monkeypatch):
    """App Streamlit apontado para o banco de testes (commits reais, tabelas limpas antes e depois)."""
    monkeypatch.setenv("DATABASE_URL", test_url)
    db_session.get_engine.cache_clear()
    db_session._session_factory.cache_clear()
    monkeypatch.setattr(autenticacao, "_rounds", 4)
    monkeypatch.setattr(autenticacao, "_limitador", LimitadorTentativas())

    def limpar():
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE usuario RESTART IDENTITY CASCADE"))
            conn.execute(text("TRUNCATE registro_auditoria"))

    limpar()
    yield AppTest.from_file(APP, default_timeout=20).run()
    limpar()
    db_session.get_engine.cache_clear()
    db_session._session_factory.cache_clear()


def _criar_conta(at, nome="Ana", email="ana@exemplo.com", senha="senha-segura-123", conf=None):
    at.text_input(key="cadastro_nome").input(nome)
    at.text_input(key="cadastro_email").input(email)
    at.text_input(key="cadastro_senha").input(senha)
    at.text_input(key="cadastro_confirmacao").input(senha if conf is None else conf)
    at.button(key="btn_cadastrar").click()
    return at.run()


def _entrar(at, email="ana@exemplo.com", senha="senha-segura-123"):
    at.text_input(key="entrar_email").input(email)
    at.text_input(key="entrar_senha").input(senha)
    at.button(key="btn_entrar").click()
    return at.run()


def test_sem_login_so_aparece_a_tela_de_acesso(app):
    assert not app.exception
    assert [t.label for t in app.tabs] == ["Entrar", "Criar conta"]
    assert len(app.sidebar.button) == 0  # sem botão "Sair" nem navegação
    assert not any("Olá" in m.value for m in app.markdown)


def test_criar_conta_e_entrar(app):
    app = _criar_conta(app)
    assert any("Conta criada" in s.value for s in app.success)
    assert not any("Olá" in m.value for m in app.markdown)  # criar conta não autentica

    app = _entrar(app)
    assert not app.exception
    assert any("Olá, **Ana**" in m.value for m in app.markdown)
    assert any("Conectado como **Ana**" in m.value for m in app.sidebar.markdown)


def test_cadastro_invalido_mostra_erros(app):
    app = _criar_conta(app, email="invalido", senha="curta", conf="curta")
    mensagens = " ".join(e.value for e in app.error)
    assert "e-mail válido" in mensagens and "pelo menos 8" in mensagens
    assert not app.success


def test_cadastro_com_email_duplicado(app):
    app = _criar_conta(app)
    app = _criar_conta(app)
    assert any("já está cadastrado" in e.value for e in app.error)


def test_login_invalido_nao_autentica(app):
    app = _criar_conta(app)
    app = _entrar(app, senha="senha-errada-9")
    assert any("incorretos" in e.value for e in app.error)
    assert not any("Olá" in m.value for m in app.markdown)


def test_sair_volta_para_a_tela_de_acesso(app):
    app = _criar_conta(app)
    app = _entrar(app)
    app.sidebar.button(key="btn_sair").click()
    app = app.run()
    assert [t.label for t in app.tabs] == ["Entrar", "Criar conta"]
    assert not any("Olá" in m.value for m in app.markdown)


def test_pagina_protegida_recusa_acesso_sem_login(app):
    """Defesa em profundidade: mesmo chamada diretamente, a página inicial exige login."""
    from streamlit.testing.v1 import AppTest

    def script():
        from sgr.ui.pagina_inicio import pagina_inicio
        pagina_inicio()

    at = AppTest.from_function(script, default_timeout=20).run()
    assert any("Faça login" in e.value for e in at.error)
    assert not any("Olá" in m.value for m in at.markdown)
