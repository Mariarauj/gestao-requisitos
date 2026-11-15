"""Ponto de entrada do Streamlit: streamlit run app.py

Sem login, só a tela de acesso (entrar / criar conta) é exibida. Depois do login, as
páginas do sistema entram na navegação; novas páginas devem ser adicionadas à lista abaixo.
"""
import streamlit as st

from sgr.ui import navegacao
from sgr.ui.pagina_acesso import pagina_acesso
from sgr.ui.pagina_backlogs import pagina_backlogs
from sgr.ui.pagina_inicio import pagina_inicio
from sgr.ui.pagina_projetos import pagina_projetos
from sgr.ui.sessao import encerrar_sessao, usuario_logado

st.set_page_config(page_title="SGR", page_icon="📋")

usuario = usuario_logado()
if usuario is None:
    pagina_acesso()
    st.stop()

with st.sidebar:
    st.write(f"Conectado como **{usuario.nome}**")
    if st.button("Sair", key="btn_sair"):
        encerrar_sessao()
        st.rerun()

paginas = {
    "inicio": st.Page(pagina_inicio, title="Início", icon="🏠", default=True),
    "projetos": st.Page(pagina_projetos, title="Projetos", icon="📁", url_path="projetos"),
    "backlogs": st.Page(pagina_backlogs, title="Backlogs", icon="🗂️", url_path="backlogs"),
}
navegacao.registrar(paginas)  # habilita os atalhos "Ir para..." entre as telas
st.navigation(list(paginas.values())).run()
