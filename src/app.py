"""Ponto de entrada do Streamlit: streamlit run app.py

Por enquanto exibe apenas o estado da conexão com o banco. As páginas do sistema
serão adicionadas em sgr/ui/.
"""
import streamlit as st
from sqlalchemy import inspect, text

from sgr.db import get_engine

st.set_page_config(page_title="SGR", page_icon="📋")
st.title("Sistema de Gestão de Requisitos")

try:
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    tabelas = sorted(t for t in inspect(engine).get_table_names() if t != "alembic_version")
    st.success("Conexão com o banco de dados estabelecida.")
    if tabelas:
        st.caption(f"{len(tabelas)} tabelas: " + ", ".join(tabelas))
    else:
        st.warning("Banco vazio. Execute `alembic upgrade head` para criar as tabelas.")
except Exception as erro:  # noqa: BLE001
    st.error("Não foi possível conectar ao banco de dados.")
    st.exception(erro)
