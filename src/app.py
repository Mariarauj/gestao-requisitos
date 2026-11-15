"""Ponto de entrada do Streamlit: streamlit run app.py

Sem sessão válida, só as telas de acesso aparecem (entrar, criar conta, sessão expirada). A
verificação roda a cada execução da página, então um endereço digitado não contorna o login
(Storyboard 1, Q-06). Depois do login, as páginas do sistema entram na navegação; novas páginas
devem ser adicionadas à lista abaixo.
"""
import streamlit as st

from sgr.ui.conta import menu_do_usuario
from sgr.ui.pagina_acesso import conta_recem_criada, pagina_acesso, tela_conta_criada
from sgr.ui.pagina_backlogs import pagina_backlogs
from sgr.ui.pagina_inicio import pagina_inicio
from sgr.ui.pagina_projetos import pagina_projetos
from sgr.ui.sessao import EstadoSessao, registrar_acesso_direto, usuario_logado, verificar_sessao

st.set_page_config(page_title="SGR", page_icon="📋")

pagina_projetos_ = st.Page(pagina_projetos, title="Projetos", icon="📁", url_path="projetos")
paginas = [
    st.Page(pagina_inicio, title="Início", icon="🏠", default=True),
    pagina_projetos_,
    st.Page(pagina_backlogs, title="Backlogs", icon="🗂️", url_path="backlogs"),
]

if verificar_sessao() is not EstadoSessao.ATIVA:
    registrar_acesso_direto({p.url_path for p in paginas if p.url_path})
    pagina_acesso()
    st.stop()

if conta_recem_criada():
    tela_conta_criada()
    st.stop()

menu_do_usuario(usuario_logado())

if st.session_state.pop("ir_para_projetos", False):  # "Começar agora" (Q-04)
    st.switch_page(pagina_projetos_)
aviso = st.session_state.pop("aviso_boas_vindas", None)
if aviso:
    st.toast(aviso, icon="👋")

st.navigation(paginas).run()
