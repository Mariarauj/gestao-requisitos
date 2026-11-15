"""Diálogos de história (Storyboard 3: Q-15, Q-16, Q-21 e Q-22).

- Q-15/Q-16 nova história e edição: papel, ação e benefício em campos separados, frase montada
  em tempo real, story points, etiqueta MoSCoW e épicos; o erro aparece no próprio campo e o
  que foi digitado permanece na tela.
- Q-21 vincular a épicos: seleção múltipla, restrita aos épicos do mesmo projeto.
- Q-22 exclusão com o inventário do que será removido.
"""
import streamlit as st

from sgr.services import epicos, historias
from sgr.services.auth_service import ErroDeValidacao
from sgr.services.historia_service import (
    MOSCOW,
    STORY_POINTS,
    HistoriaDados,
    HistoriaNaoEncontrada,
    ProductBacklogInexistente,
)
from sgr.ui import navegacao
from sgr.ui.formatos import MOSCOW_NOMES, nota, plural

_VAZIO = "______"
_NOTA_EPICOS = "Só épicos deste projeto podem ser vinculados; épicos de outros projetos não aparecem aqui."


def frase_da_historia(papel: str, acao: str, beneficio: str) -> str:
    """Pré-visualização: o que ainda não foi digitado aparece como linha em branco."""
    return (
        f"Como um {papel.strip() or _VAZIO}, eu quero {acao.strip() or _VAZIO}, "
        f"para {beneficio.strip() or _VAZIO}."
    )


def _pontos(valor: int | None) -> str:
    return "Sem estimativa" if valor is None else str(valor)


def dialogo_historia(usuario_id: int, projeto_id: int, historia: HistoriaDados | None = None) -> None:
    """Nova história (historia=None) ou edição de uma existente."""
    editando = historia is not None
    p = f"hf{historia.id if editando else 'nova'}_"
    lista_epicos = epicos.listar(usuario_id, projeto_id)
    nomes_epicos = {e.id: e.nome for e in lista_epicos}

    def corpo() -> None:
        st.caption("Product backlog" if not editando else f"{historia.codigo} · {historia.backlog_nome}")
        papel = st.text_input("Como um ★", value=historia.papel if editando else "", key=p + "papel",
                              placeholder="papel ou persona", help="Quem precisa desta funcionalidade.")
        erro_papel = st.empty()
        acao = st.text_input("eu quero ★", value=historia.acao if editando else "", key=p + "acao",
                             placeholder="ação", help="O que a pessoa quer fazer.")
        erro_acao = st.empty()
        beneficio = st.text_input("para ★", value=historia.beneficio if editando else "", key=p + "beneficio",
                                  placeholder="benefício", help="Por que isso importa.")
        erro_beneficio = st.empty()
        st.markdown("**Pré-visualização**")
        st.info(frase_da_historia(papel, acao, beneficio))

        pontos = st.selectbox(
            "Story points", [None, *STORY_POINTS], key=p + "pontos", format_func=_pontos,
            index=([None, *STORY_POINTS].index(historia.story_points) if editando else 0),
            help="Valores: " + ", ".join(str(v) for v in STORY_POINTS),
        )
        erro_pontos = st.empty()
        moscow = st.selectbox(
            "Etiqueta MoSCoW", list(MOSCOW), key=p + "moscow",
            format_func=lambda v: f"{v} · {MOSCOW_NOMES[v]}",
            index=list(MOSCOW).index(historia.moscow) if editando else list(MOSCOW).index("S"),
        )
        erro_moscow = st.empty()
        escolhidos: list[int] = []
        if not editando:  # na edição, os épicos mudam pelo diálogo "Vincular a épicos" (Q-21)
            escolhidos = st.multiselect("Épicos", list(nomes_epicos), key=p + "epicos",
                                        format_func=nomes_epicos.get, placeholder="Adicionar épico...")
            st.caption(_NOTA_EPICOS)
            if not nomes_epicos:
                st.caption("Este projeto ainda não tem épicos. Crie um na página Épicos.")
        erro_epicos = st.empty()

        c_cancelar, c_criterios, c_salvar = st.columns([2, 4, 3])
        cancelar = c_cancelar.button("Cancelar", key=p + "cancelar")
        if editando:
            criterios = False
            salvar = c_salvar.button("Salvar alterações", type="primary", key=p + "salvar")
        else:
            criterios = c_criterios.button("Salvar e adicionar critérios", key=p + "criterios")
            salvar = c_salvar.button("Criar história", type="primary", key=p + "salvar")
        if cancelar:
            st.rerun()
        if not (salvar or criterios):
            return
        try:
            if editando:
                salva = historias.atualizar(usuario_id, historia.id, papel, acao, beneficio, pontos, moscow)
            else:
                salva = historias.criar(usuario_id, projeto_id, papel, acao, beneficio, pontos, moscow, escolhidos)
        except ErroDeValidacao as erro:  # nada é apagado: a pessoa só corrige o campo apontado
            destinos = {"papel": erro_papel, "acao": erro_acao, "beneficio": erro_beneficio,
                        "story_points": erro_pontos, "moscow": erro_moscow, "epicos": erro_epicos}
            for campo, mensagem in erro.erros.items():
                destinos.get(campo, erro_epicos).error(mensagem)
            return
        except (ProductBacklogInexistente, HistoriaNaoEncontrada) as erro:
            st.error(str(erro))
            return
        st.session_state[navegacao.AVISO_HISTORIA] = "✓ História atualizada." if editando else "✓ História criada."
        if criterios:  # encadeia com o cadastro de critérios (Q-15)
            st.session_state[navegacao.HISTORIA_ABERTA] = salva.id
            st.session_state[navegacao.CRITERIO_REABRIR] = salva.id
        st.rerun()

    st.dialog("Editar história" if editando else "Nova história de usuário")(corpo)()


def dialogo_epicos(usuario_id: int, historia: HistoriaDados) -> None:
    """Q-21: escolhe os épicos da história (substitui o conjunto atual)."""
    lista = epicos.listar(usuario_id, historia.projeto_id)
    nomes = {e.id: e for e in lista}
    p = f"ve{historia.id}_"

    def corpo() -> None:
        if not lista:
            st.info("Este projeto ainda não tem épicos. Crie um na página Épicos.")
            if st.button("Fechar", key=p + "fechar"):
                st.rerun()
            return
        escolhidos = st.multiselect(
            "Épicos", list(nomes), default=[e.id for e in historia.epicos if e.id in nomes], key=p + "epicos",
            format_func=lambda i: f"{nomes[i].nome} · {plural(nomes[i].historias, 'história', 'histórias')}",
            placeholder="Buscar épico...",
        )
        st.caption(_NOTA_EPICOS)
        erro = st.empty()
        c1, c2 = st.columns(2)
        if c1.button("Cancelar", key=p + "cancelar"):
            st.rerun()
        if c2.button("Vincular selecionados", type="primary", key=p + "vincular"):
            try:
                historias.definir_epicos(usuario_id, historia.id, escolhidos)
            except ErroDeValidacao as e:
                erro.error(" ".join(e.erros.values()))
                return
            except HistoriaNaoEncontrada as e:
                erro.error(str(e))
                return
            st.session_state[navegacao.AVISO_HISTORIA] = "✓ Épicos atualizados."
            st.rerun()

    st.dialog(f"Vincular {historia.codigo} a épicos")(corpo)()


def dialogo_exclusao(usuario_id: int, historia: HistoriaDados) -> None:
    """Q-22: mostra o que será removido junto e exige o reconhecimento da irreversibilidade."""
    inventario = historias.inventario(usuario_id, historia.id)
    p = f"hx{historia.id}_"

    def corpo() -> None:
        st.markdown(f"**Excluir a história {historia.codigo}?**")
        st.caption(historia.frase)
        st.write("Ao excluir, também serão removidos:")
        st.markdown(f"- {plural(inventario.criterios, 'critério de aceitação', 'critérios de aceitação')}")
        st.markdown(f"- vínculo com {plural(inventario.epicos, 'épico', 'épicos')}")
        estimativa = [f"estimativa de {historia.story_points} pontos"] if historia.story_points is not None else []
        estimativa += [f"etiqueta {historia.moscow}"]
        if historia.rice is not None:
            estimativa.append(f"nota RICE {nota(historia.rice)}")
        st.markdown("- " + ", ".join(estimativa))
        ciente = st.checkbox("Entendo que esta ação não pode ser desfeita.", key=p + "ciente")
        c1, c2 = st.columns(2)
        if c1.button("Cancelar", key=p + "cancelar"):
            st.rerun()
        if c2.button("Excluir definitivamente", type="primary", disabled=not ciente, key=p + "excluir"):
            try:
                historias.excluir(usuario_id, historia.id)
            except HistoriaNaoEncontrada:
                pass  # já não existe: o resultado é o mesmo
            st.session_state[navegacao.AVISO_HISTORIA] = "✓ História excluída."
            st.session_state.pop(navegacao.HISTORIA_ABERTA, None)
            st.rerun()

    st.dialog(f"Excluir {historia.codigo}")(corpo)()
