"""Ponto de entrada do Streamlit: streamlit run app.py

Sem sessão válida, só as telas de acesso são exibidas (entrar, criar conta, sessão expirada,
acesso direto a endereço interno). Depois do login, as páginas do sistema entram na navegação;
novas páginas devem ser adicionadas à lista abaixo.
"""
import streamlit as st

from sgr.ui import conta, navegacao
from sgr.ui import sessao as ses
from sgr.ui.pagina_acesso import conta_recem_criada, pagina_acesso, tela_conta_criada
from sgr.ui.pagina_backlogs import pagina_backlogs
from sgr.ui.pagina_epicos import pagina_epicos
from sgr.ui.pagina_historias import pagina_historias
from sgr.ui.pagina_inicio import pagina_inicio
from sgr.ui.pagina_projetos import pagina_projetos

st.set_page_config(page_title="SGR", page_icon="📋")

PAGINAS_PROTEGIDAS = {"projetos", "backlogs", "historias", "epicos"}  # url_path das páginas internas

# Confere a sessão a cada execução: o prazo de inatividade vale também para o endereço digitado.
if ses.verificar_sessao() is not ses.EstadoSessao.ATIVA:
    ses.registrar_acesso_direto(PAGINAS_PROTEGIDAS)
    pagina_acesso()
    st.stop()

usuario = ses.usuario_logado()

if conta_recem_criada():  # Q-04: confirmação logo após o cadastro
    tela_conta_criada()
    st.stop()

conta.menu_do_usuario(usuario)

paginas = {
    "inicio": st.Page(pagina_inicio, title="Início", icon="🏠", default=True),
    "projetos": st.Page(pagina_projetos, title="Projetos", icon="📁", url_path="projetos"),
    "backlogs": st.Page(pagina_backlogs, title="Backlogs", icon="🗂️", url_path="backlogs"),
    "historias": st.Page(pagina_historias, title="Histórias", icon="📝", url_path="historias"),
    "epicos": st.Page(pagina_epicos, title="Épicos", icon="🧩", url_path="epicos"),
}
navegacao.registrar(paginas)  # habilita os atalhos "Ir para..." entre as telas

if st.session_state.pop("ir_para_projetos", False):  # "Começar agora"
    navegacao.ir_para("projetos")

aviso = st.session_state.pop("aviso_boas_vindas", None)  # mostrado já na página de destino
if aviso:
    st.toast(aviso)

st.navigation(list(paginas.values())).run()
