"""Estado de autenticação da sessão do navegador (st.session_state).

Só guarda id, nome e e-mail. A sessão é perdida ao recarregar a página (limitação aceita
no protótipo, registrada no architecture notebook).
"""
import streamlit as st

from sgr.services.auth_service import UsuarioAutenticado

_CHAVE = "usuario_autenticado"


def usuario_logado() -> UsuarioAutenticado | None:
    return st.session_state.get(_CHAVE)


def iniciar_sessao(usuario: UsuarioAutenticado) -> None:
    st.session_state[_CHAVE] = usuario


def encerrar_sessao() -> None:
    # Limpa todo o estado, inclusive campos de formulário, para não vazar dados entre usuários.
    st.session_state.clear()


def exigir_login() -> UsuarioAutenticado:
    """Use no início de toda página protegida: interrompe a página se não houver login."""
    usuario = usuario_logado()
    if usuario is None:
        st.error("Faça login para acessar esta página.")
        st.stop()
    return usuario
