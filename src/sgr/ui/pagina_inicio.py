"""Página inicial (protegida)."""
import streamlit as st

from sgr.services.sistema_service import tabelas_do_banco
from sgr.ui.sessao import exigir_login


def pagina_inicio() -> None:
    usuario = exigir_login()
    st.title("Sistema de Gestão de Requisitos")
    st.write(f"Olá, **{usuario.nome}**!")
    try:
        tabelas = tabelas_do_banco()
        st.success("Conexão com o banco de dados estabelecida.")
        if tabelas:
            st.caption(f"{len(tabelas)} tabelas: " + ", ".join(tabelas))
        else:
            st.warning("Banco vazio. Execute `alembic upgrade head` para criar as tabelas.")
    except Exception as erro:  # noqa: BLE001
        st.error("Não foi possível conectar ao banco de dados.")
        st.exception(erro)
