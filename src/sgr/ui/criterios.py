"""Critérios de aceitação da história (Storyboard 3: Q-19 e Q-20).

Formato Dado / Quando / Então em campos separados, com a frase montada antes de salvar. Os
critérios cadastrados são editados no lugar (sem formulário novo) e excluídos com confirmação.
Cada critério pertence a uma única história.
"""
import streamlit as st

from sgr.services import criterios
from sgr.services.auth_service import ErroDeValidacao
from sgr.services.criterio_service import CriterioNaoEncontrado
from sgr.services.historia_service import CriterioDados, HistoriaDados, HistoriaNaoEncontrada
from sgr.ui import navegacao
from sgr.ui.formatos import plural

_EDITANDO = "criterio_em_edicao"
_VAZIO = "______"


def frase_do_criterio(contexto: str, acao: str, resultado: str) -> str:
    return (
        f"Dado {contexto.strip() or _VAZIO}, quando {acao.strip() or _VAZIO}, "
        f"então {resultado.strip() or _VAZIO}."
    )


def _mostrar_erros(erro: ErroDeValidacao, destinos: dict) -> None:
    for campo, mensagem in erro.erros.items():
        destinos[campo].error(mensagem)


def dialogo_criterio(usuario_id: int, historia: HistoriaDados) -> None:
    """Q-19: novo critério. 'Salvar e adicionar outro' reabre o diálogo em branco."""
    p = f"nc{historia.id}_"

    def corpo() -> None:
        st.caption(f"{historia.codigo} · {historia.frase}")
        contexto = st.text_input("Dado ★", key=p + "contexto", placeholder="que estou na página de produtos",
                                 help="Contexto inicial ou estado do sistema antes da ação.")
        erro_contexto = st.empty()
        acao = st.text_input("Quando ★", key=p + "acao", placeholder="seleciono a categoria Eletrônicos",
                             help="Ação ou evento que o usuário executa.")
        erro_acao = st.empty()
        resultado = st.text_input("Então ★", key=p + "resultado", placeholder="vejo apenas produtos dessa categoria",
                                  help="Resultado esperado ou consequência.")
        erro_resultado = st.empty()
        st.markdown("**Pré-visualização**")
        st.info(frase_do_criterio(contexto, acao, resultado))

        c_cancelar, c_outro, c_salvar = st.columns([2, 4, 3])
        cancelar = c_cancelar.button("Cancelar", key=p + "cancelar")
        outro = c_outro.button("Salvar e adicionar outro", key=p + "outro")
        salvar = c_salvar.button("Salvar critério", type="primary", key=p + "salvar")
        if cancelar:
            st.rerun()
        if not (outro or salvar):
            return
        try:
            criterios.criar(usuario_id, historia.id, contexto, acao, resultado)
        except ErroDeValidacao as erro:
            _mostrar_erros(erro, {"contexto": erro_contexto, "acao": erro_acao, "resultado": erro_resultado})
            return
        except HistoriaNaoEncontrada as erro:
            st.error(str(erro))
            return
        st.session_state[navegacao.AVISO_HISTORIA] = "✓ Critério salvo."
        if outro:
            st.session_state[navegacao.CRITERIO_REABRIR] = historia.id
        st.rerun()

    st.dialog("Novo critério de aceitação")(corpo)()


def dialogo_exclusao(usuario_id: int, criterio: CriterioDados) -> None:
    def corpo() -> None:
        st.markdown("**Excluir este critério de aceitação?**")
        st.caption(criterio.frase)
        c1, c2 = st.columns(2)
        if c1.button("Cancelar", key=f"cx{criterio.id}_cancelar"):
            st.rerun()
        if c2.button("Excluir critério", type="primary", key=f"cx{criterio.id}_excluir"):
            try:
                criterios.excluir(usuario_id, criterio.id)
            except CriterioNaoEncontrado:
                pass  # já não existe
            st.session_state[navegacao.AVISO_HISTORIA] = "✓ Critério excluído."
            st.rerun()

    st.dialog("Excluir critério")(corpo)()


def _editar_no_lugar(usuario_id: int, c: CriterioDados) -> None:
    """Q-20: os três campos aparecem no lugar do texto do critério."""
    p = f"ec{c.id}_"
    contexto = st.text_input("Dado", value=c.contexto, key=p + "contexto")
    erro_contexto = st.empty()
    acao = st.text_input("Quando", value=c.acao, key=p + "acao")
    erro_acao = st.empty()
    resultado = st.text_input("Então", value=c.resultado, key=p + "resultado")
    erro_resultado = st.empty()
    salvar, cancelar = st.columns(2)
    if cancelar.button("Cancelar", key=p + "cancelar"):
        st.session_state.pop(_EDITANDO, None)
        st.rerun()
    if salvar.button("Salvar", type="primary", key=p + "salvar"):
        try:
            criterios.atualizar(usuario_id, c.id, contexto, acao, resultado)
        except ErroDeValidacao as erro:
            _mostrar_erros(erro, {"contexto": erro_contexto, "acao": erro_acao, "resultado": erro_resultado})
            return
        except CriterioNaoEncontrado as erro:
            st.error(str(erro))
            return
        st.session_state.pop(_EDITANDO, None)
        st.session_state[navegacao.AVISO_HISTORIA] = "✓ Critério atualizado."
        st.rerun()


def secao(usuario_id: int, historia: HistoriaDados) -> None:
    """Lista de critérios da história (já carregada com obter) e o botão de adicionar."""
    topo, novo = st.columns([6, 3], vertical_alignment="center")
    topo.markdown(f"**Critérios de aceitação ({len(historia.criterios)})**")
    if novo.button("+ Adicionar critério", key="btn_novo_criterio"):
        dialogo_criterio(usuario_id, historia)
    if not historia.criterios:
        st.caption("Esta história ainda não tem critérios de aceitação.")
    em_edicao = st.session_state.get(_EDITANDO)
    for numero, c in enumerate(historia.criterios, start=1):
        with st.container(border=True):
            if c.id == em_edicao:
                st.markdown(f"**{numero}**")
                _editar_no_lugar(usuario_id, c)
                continue
            texto, editar, excluir = st.columns([12, 1, 1], vertical_alignment="center")
            texto.markdown(f"**{numero}** · {c.frase}.")
            if editar.button("✎", key=f"btn_editar_criterio_{c.id}", help="Editar critério"):
                st.session_state[_EDITANDO] = c.id
                st.rerun()
            if excluir.button("🗑", key=f"btn_excluir_criterio_{c.id}", help="Excluir critério"):
                dialogo_exclusao(usuario_id, c)
    st.caption("Cada critério pertence a esta história e não pode ser reutilizado em outra.")
    if historia.criterios:
        st.caption(plural(len(historia.criterios), "critério cadastrado", "critérios cadastrados"))
