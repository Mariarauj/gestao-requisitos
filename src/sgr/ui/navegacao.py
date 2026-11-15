"""Navegação entre páginas por atalhos (ex.: "Ir para: Product Backlog" no painel do projeto).

O app.py registra as páginas uma vez por execução; as páginas só pedem "ir para X", sem
conhecer objetos st.Page. Um destino que ainda não foi registrado (tela que ainda não existe)
aparece como indisponível, e passa a funcionar sozinho quando a página entrar no app.py.

Também concentra as chaves de st.session_state que uma página lê para abrir já no contexto
certo (projeto e backlog escolhidos), para que quem navega e quem recebe usem o mesmo nome.
"""
import streamlit as st

_PAGINAS = "_paginas_registradas"

# estado lido pela página de Backlogs
PROJETO_DOS_BACKLOGS = "backlogs_projeto_id"
BACKLOG_ABERTO = "backlog_aberto"


def registrar(paginas: dict[str, object]) -> None:
    """Guarda as páginas da navegação, por nome curto ("projetos", "backlogs", ...)."""
    st.session_state[_PAGINAS] = dict(paginas)


def disponivel(destino: str) -> bool:
    return destino in st.session_state.get(_PAGINAS, {})


def ir_para(destino: str, **estado) -> None:
    """Define o estado da página de destino e troca de página.

    Valor None em `estado` remove a chave (ex.: BACKLOG_ABERTO=None abre a lista, não um backlog).
    """
    for chave, valor in estado.items():
        if valor is None:
            st.session_state.pop(chave, None)
        else:
            st.session_state[chave] = valor
    st.switch_page(st.session_state[_PAGINAS][destino])
