"""Seletor de projeto compartilhado pelas páginas de Histórias e de Épicos.

Usa a mesma chave de estado da página de Backlogs, para que o projeto escolhido acompanhe a
pessoa entre as telas.
"""
import streamlit as st

from sgr.services import projetos
from sgr.ui import navegacao


def escolher_projeto(usuario_id: int, chave: str, destino: str) -> tuple[int, str] | None:
    """Mostra o seletor e devolve (id, nome) do projeto escolhido, ou None se não houver projeto.

    `chave` é a chave do widget (uma por página); `destino` completa a mensagem de projeto vazio.
    """
    lista = projetos.listar(usuario_id)
    if not lista:
        st.info(f"Crie um projeto na página Projetos para gerenciar {destino}.")
        return None
    ids = [p.id for p in lista]
    nomes = {p.id: p.nome for p in lista}
    atual = st.session_state.get(navegacao.PROJETO_DOS_BACKLOGS)
    if atual not in ids:
        atual = st.session_state.get("projeto_aberto")
    if atual not in ids:
        atual = ids[0]
    escolhido = st.selectbox("Projeto", ids, index=ids.index(atual), format_func=nomes.get, key=chave)
    anterior = st.session_state.get(navegacao.PROJETO_DOS_BACKLOGS)
    if anterior is not None and anterior != escolhido:
        st.session_state.pop(navegacao.HISTORIA_ABERTA, None)  # outro projeto: fecha a história aberta
    st.session_state[navegacao.PROJETO_DOS_BACKLOGS] = escolhido
    return escolhido, nomes[escolhido]
