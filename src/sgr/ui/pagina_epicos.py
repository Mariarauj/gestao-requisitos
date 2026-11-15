"""Épicos (Storyboard 3: criação em modal e painel de épicos do Q-21; requisito 10).

Lista os épicos do projeto com a quantidade de histórias e de pontos de cada um, e permite
criar, editar e excluir. Um épico com histórias não pode ser excluído: primeiro desfaça os
vínculos. O wireframe mostra também "N de M histórias concluídas"; como a história ainda não
tem estado de conclusão no modelo, o painel mostra histórias e pontos.
"""
import streamlit as st

from sgr.services import epicos
from sgr.services.auth_service import ErroDeValidacao
from sgr.services.epico_service import (
    DESCRICAO_MAX,
    NOME_MAX,
    EpicoComHistorias,
    EpicoDados,
    EpicoNaoEncontrado,
)
from sgr.services.projeto_service import ProjetoNaoEncontrado
from sgr.ui import navegacao
from sgr.ui.formatos import plural
from sgr.ui.seletor import escolher_projeto
from sgr.ui.sessao import exigir_login


def _exibir_aviso() -> None:
    mensagem = st.session_state.pop(navegacao.AVISO_EPICO, None)
    if mensagem:
        st.toast(mensagem, icon="✅")


def dialogo_epico(usuario_id: int, projeto_id: int, epico: EpicoDados | None = None) -> None:
    editando = epico is not None
    p = f"ep{epico.id if editando else 'novo'}_"

    def corpo() -> None:
        nome = st.text_input("Nome ★", value=epico.nome if editando else "", key=p + "nome",
                             max_chars=NOME_MAX, placeholder="Ex.: Catálogo")
        erro_nome = st.empty()
        descricao = st.text_area("Descrição", value=(epico.descricao or "") if editando else "",
                                 key=p + "descricao", max_chars=DESCRICAO_MAX)
        erro_descricao = st.empty()
        c1, c2 = st.columns(2)
        if c1.button("Cancelar", key=p + "cancelar"):
            st.rerun()
        if not c2.button("Salvar" if editando else "Criar épico", type="primary", key=p + "salvar"):
            return
        try:
            if editando:
                epicos.atualizar(usuario_id, epico.id, nome, descricao)
            else:
                epicos.criar(usuario_id, projeto_id, nome, descricao)
        except ErroDeValidacao as erro:  # inclui "nome já usado": o texto digitado permanece
            destinos = {"nome": erro_nome, "descricao": erro_descricao}
            for campo, mensagem in erro.erros.items():
                destinos[campo].error(mensagem)
            return
        except (EpicoNaoEncontrado, ProjetoNaoEncontrado) as erro:
            st.error(str(erro))
            return
        st.session_state[navegacao.AVISO_EPICO] = "✓ Épico atualizado." if editando else "✓ Épico criado."
        st.rerun()

    st.dialog("Editar épico" if editando else "Novo épico")(corpo)()


def dialogo_exclusao(usuario_id: int, epico: EpicoDados) -> None:
    p = f"epx{epico.id}_"

    def corpo() -> None:
        st.markdown(f"**Excluir o épico {epico.nome}?**")
        bloqueado = epico.historias > 0
        if bloqueado:
            st.warning(str(EpicoComHistorias(epico.historias)))
        else:
            st.caption("Esta ação não pode ser desfeita.")
        c1, c2 = st.columns(2)
        if c1.button("Cancelar", key=p + "cancelar"):
            st.rerun()
        if c2.button("Excluir épico", type="primary", disabled=bloqueado, key=p + "excluir"):
            try:
                epicos.excluir(usuario_id, epico.id)
            except EpicoComHistorias as erro:  # alguém vinculou uma história desde que a lista foi lida
                st.error(str(erro))
                return
            except EpicoNaoEncontrado:
                pass  # já não existe
            st.session_state[navegacao.AVISO_EPICO] = "✓ Épico excluído."
            st.rerun()

    st.dialog("Excluir épico")(corpo)()


def _cartao(usuario_id: int, e: EpicoDados) -> None:
    with st.container(border=True):
        corpo, editar, excluir = st.columns([8, 2, 2], vertical_alignment="center")
        corpo.markdown(f"**{e.nome}**")
        if e.descricao:
            corpo.write(e.descricao)
        corpo.caption(f"{plural(e.historias, 'história', 'histórias')} · {plural(e.pontos, 'ponto', 'pontos')}")
        if editar.button("Editar", key=f"btn_editar_epico_{e.id}"):
            dialogo_epico(usuario_id, e.projeto_id, e)
        if excluir.button("🗑 Excluir", key=f"btn_excluir_epico_{e.id}"):
            dialogo_exclusao(usuario_id, e)
        if e.historias:
            with st.expander("Histórias deste épico"):
                for h in epicos.obter(usuario_id, e.id).historias:
                    st.markdown(f"**{h.codigo}** · Como um {h.papel}, eu quero {h.acao}, para {h.beneficio}")


def pagina_epicos() -> None:
    usuario = exigir_login()
    _exibir_aviso()
    st.title("Épicos")
    escolha = escolher_projeto(usuario.id, "seletor_projeto_epicos", "os épicos")
    if escolha is None:
        return
    projeto_id, projeto_nome = escolha
    if st.button("+ Novo épico", type="primary", key="btn_novo_epico"):
        dialogo_epico(usuario.id, projeto_id)
    lista = epicos.listar(usuario.id, projeto_id)
    if not lista:
        st.caption(f"{projeto_nome} ainda não tem épicos. Crie o primeiro para agrupar histórias por tema.")
    for e in lista:
        _cartao(usuario.id, e)
