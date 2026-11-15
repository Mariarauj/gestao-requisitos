"""Atalhos entre páginas (sgr.ui.navegacao): troca real de página do Streamlit."""
from streamlit.testing.v1 import AppTest

from sgr.db import session as db_session


def _mini_app():
    import streamlit as st

    from sgr.ui import navegacao

    def a():
        st.write("PAGINA A")
        st.write(f"b disponível: {navegacao.disponivel('b')} / c disponível: {navegacao.disponivel('c')}")
        if st.button("ir", key="ir"):
            navegacao.ir_para("b", chave_nova=7, chave_removida=None)

    def b():
        st.write(f"PAGINA B nova={st.session_state.get('chave_nova')} removida={st.session_state.get('chave_removida')}")

    pa = st.Page(a, title="A", url_path="a", default=True)
    pb = st.Page(b, title="B", url_path="b")
    navegacao.registrar({"a": pa, "b": pb})
    st.navigation([pa, pb]).run()


def test_disponivel_reflete_as_paginas_registradas():
    at = AppTest.from_function(_mini_app, default_timeout=20).run()
    assert "b disponível: True / c disponível: False" in [m.value for m in at.markdown]


def test_ir_para_troca_de_pagina_define_estado_e_remove_chave_com_none():
    at = AppTest.from_function(_mini_app, default_timeout=20).run()
    at.session_state["chave_removida"] = "resíduo"
    at.button(key="ir").click()
    at = at.run()
    assert not at.exception
    assert [m.value for m in at.markdown] == ["PAGINA B nova=7 removida=None"]


def test_app_real_registra_as_paginas_do_sistema(engine, test_url, monkeypatch):
    from sgr.services.auth_service import UsuarioAutenticado

    monkeypatch.setenv("DATABASE_URL", test_url)  # a página Início consulta o banco
    db_session.get_engine.cache_clear()
    db_session._session_factory.cache_clear()
    at = AppTest.from_file(__file__.replace("tests/test_ui_navegacao.py", "app.py"), default_timeout=30)
    at.session_state["usuario_autenticado"] = UsuarioAutenticado(1, "Ana", "ana@x.com")
    at.run()
    assert not at.exception
    assert set(at.session_state["_paginas_registradas"]) == {"inicio", "projetos", "backlogs", "historias", "epicos"}
    db_session.get_engine.cache_clear()
    db_session._session_factory.cache_clear()
