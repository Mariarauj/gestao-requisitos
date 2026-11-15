"""Identificação do usuário e menu da conta na barra lateral (Storyboard 1, Q-05 e Q-07 A).

Não há "Preferências de exibição" (Q-05): o sistema ainda não tem preferências a configurar.
"""
import streamlit as st

from sgr.services.auth_service import UsuarioAutenticado
from sgr.ui import sessao as ses


def iniciais(nome: str) -> str:
    """'Maria Araújo' -> 'MA'; nome de uma palavra só usa as duas primeiras letras."""
    partes = nome.split()
    if not partes:
        return "?"
    letras = partes[0][0] + partes[-1][0] if len(partes) > 1 else partes[0][:2]
    return letras.upper()


@st.dialog("Sair do sistema?")
def confirmar_saida() -> None:
    st.write("Você precisará entrar novamente para acessar seus projetos.")
    sair, cancelar = st.columns(2)
    if sair.button("Sair", key="btn_confirmar_saida", type="primary"):
        ses.encerrar_sessao(ses.SAIU)
        st.rerun()
    if cancelar.button("Cancelar", key="btn_cancelar_saida"):
        st.rerun()


@st.dialog("Minha conta")
def dialogo_minha_conta() -> None:
    usuario = ses.usuario_logado()
    st.text_input("Nome", value=usuario.nome, disabled=True, key="conta_nome")
    st.text_input("E-mail", value=usuario.email, disabled=True, key="conta_email")
    st.caption(ses.texto_da_sessao())
    if st.button("Fechar", key="btn_fechar_conta"):
        st.rerun()


def menu_do_usuario(usuario: UsuarioAutenticado) -> None:
    """Quem está conectado, a sessão, e o menu com Minha conta e Sair."""
    with st.sidebar:
        st.text(f"{iniciais(usuario.nome)}  {usuario.nome}")  # texto puro: o nome nunca vira markdown
        st.caption(ses.texto_da_sessao())
        with st.popover("Conta"):
            if st.button("Minha conta", key="btn_minha_conta"):
                dialogo_minha_conta()
            if st.button("Sair", key="btn_sair"):
                confirmar_saida()
