"""Histórias de um backlog e movimentação entre backlogs (Storyboard 4: Q-27, Q-28 e Q-29).

- Product backlog: lista de histórias com filtros (épico, MoSCoW), ordenação, caixas de seleção
  e a barra "Mover para..."; ao lado, o painel com os sprints do projeto.
- Sprint backlog: a mesma lista, para planejamento, com a mesma mecânica de seleção, que permite
  devolver histórias ao product backlog ou passá-las a outro sprint.
- Mover é por seleção e botão (não há arrastar e soltar). Sprint encerrado é somente leitura:
  não recebe nem libera histórias.

Não há quadro Kanban por status: a história ainda não tem status no modelo de dados.
"""
import streamlit as st

from sgr.services import backlogs, epicos, historias
from sgr.services.auth_service import ErroDeValidacao
from sgr.services.backlog_service import (
    BacklogDados,
    BacklogNaoEncontrado,
    BacklogsDoProjeto,
    SprintEncerrado,
)
from sgr.services.historia_service import HistoriaDados, HistoriaNaoEncontrada
from sgr.ui import navegacao
from sgr.ui.formatos import ESTADOS, MOSCOW_NOMES, data, nota, plural

_ORDENS = {"posicao": "Criação", "pontos": "Pontos", "moscow": "MoSCoW", "rice": "RICE"}


# ---------- seleção ----------

def _chave(backlog_id: int, historia_id: int) -> str:
    """Chave da caixa de seleção. A geração muda ao limpar a seleção: caixas novas, desmarcadas."""
    geracao = st.session_state.get(f"geracao_selecao_{backlog_id}", 0)
    return f"sel_{backlog_id}_{geracao}_{historia_id}"


def _limpar_selecao(backlog_id: int) -> None:
    chave = f"geracao_selecao_{backlog_id}"
    st.session_state[chave] = st.session_state.get(chave, 0) + 1


def _limpar_filtros(backlog_id: int) -> None:
    for prefixo in ("flt_epico", "flt_moscow", "flt_ordem"):
        st.session_state.pop(f"{prefixo}_{backlog_id}", None)


# ---------- filtros e ordenação ----------

def _filtros(usuario_id: int, b: BacklogDados) -> tuple[int | None, str | None, str]:
    lista = epicos.listar(usuario_id, b.projeto_id)
    nomes = {e.id: e.nome for e in lista}
    c_epico, c_moscow, c_ordem, c_limpar = st.columns([3, 3, 3, 2], vertical_alignment="bottom")
    epico_id = c_epico.selectbox(
        "Épico",
        [None, *nomes],
        format_func=lambda v: "Todos" if v is None else nomes[v],
        key=f"flt_epico_{b.id}",
    )
    moscow = c_moscow.selectbox(
        "MoSCoW",
        [None, *MOSCOW_NOMES],
        format_func=lambda v: "Todas" if v is None else f"{v} · {MOSCOW_NOMES[v]}",
        key=f"flt_moscow_{b.id}",
    )
    ordem = c_ordem.selectbox(
        "Ordenar por", list(_ORDENS), format_func=_ORDENS.get, key=f"flt_ordem_{b.id}"
    )
    c_limpar.button("Limpar filtros", key=f"btn_limpar_filtros_{b.id}",
                    on_click=_limpar_filtros, args=(b.id,))
    return epico_id, moscow, ordem


def _carregar(usuario_id: int, b: BacklogDados, epico_id, moscow, ordem: str) -> list[HistoriaDados]:
    por_rice = ordem == "rice"
    lista = historias.listar(
        usuario_id, b.projeto_id, backlog_id=b.id, epico_id=epico_id, moscow=moscow,
        ordenar_por="rice" if por_rice else "posicao", ordem="desc" if por_rice else None,
    )
    if ordem == "pontos":  # maior primeiro; sem estimativa por último
        lista = sorted(lista, key=lambda h: (h.story_points is None, -(h.story_points or 0), h.id))
    elif ordem == "moscow":  # M, S, C, W
        lista = sorted(lista, key=lambda h: (list(MOSCOW_NOMES).index(h.moscow), h.id))
    return lista


# ---------- lista de histórias ----------

def _linha(b: BacklogDados, h: HistoriaDados) -> None:
    with st.container(border=True):
        sel, corpo = st.columns([1, 14], vertical_alignment="center")
        sel.checkbox(f"Selecionar {h.codigo}", key=_chave(b.id, h.id),
                     label_visibility="collapsed", disabled=b.somente_leitura)
        epicos_txt = ", ".join(e.nome for e in h.epicos)
        corpo.markdown(f"**{h.codigo}**" + (f" · {epicos_txt}" if epicos_txt else ""))
        corpo.markdown(h.frase)
        pontos = f"{h.story_points} pts" if h.story_points is not None else "sem estimativa"
        rice = f"RICE {nota(h.rice)}" if h.rice is not None else "RICE pendente"
        corpo.caption(f"{pontos} · {h.moscow} · {rice}")


def _barra_selecao(usuario_id: int, b: BacklogDados, conjunto: BacklogsDoProjeto,
                   selecionadas: list[HistoriaDados]) -> None:
    with st.container(border=True):
        texto, mover, limpar = st.columns([5, 3, 3], vertical_alignment="center")
        texto.markdown(f"**{plural(len(selecionadas), 'história selecionada', 'histórias selecionadas')}**")
        if mover.button("Mover para...", type="primary", key=f"btn_mover_{b.id}"):
            todos = ([conjunto.product] if conjunto.product else []) + conjunto.sprints
            _dialogo_mover(usuario_id, b, todos, selecionadas)
        limpar.button("Limpar seleção", key=f"btn_limpar_selecao_{b.id}",
                      on_click=_limpar_selecao, args=(b.id,))


def _lista(usuario_id: int, b: BacklogDados, conjunto: BacklogsDoProjeto) -> None:
    if b.somente_leitura:
        st.info("Sprint encerrado (somente leitura): suas histórias não podem ser movidas.")
    epico_id, moscow, ordem = _filtros(usuario_id, b)
    lista = _carregar(usuario_id, b, epico_id, moscow, ordem)
    selecionadas = [h for h in lista if st.session_state.get(_chave(b.id, h.id))]
    if selecionadas and not b.somente_leitura:
        _barra_selecao(usuario_id, b, conjunto, selecionadas)
    if not lista:
        st.caption("Nenhuma história com esses filtros.")
    for h in lista:
        _linha(b, h)


# ---------- painel de sprints (Q-27) ----------

def _painel_sprints(conjunto: BacklogsDoProjeto) -> None:
    st.subheader("Sprints")
    if not conjunto.sprints:
        st.caption("Este projeto ainda não tem sprint backlogs.")
    for s in conjunto.sprints:
        with st.container(border=True):
            st.markdown(f"**{s.nome}**")
            st.caption(f"{data(s.data_inicio)} a {data(s.data_fim)} · {ESTADOS.get(s.estado or '', '')}")
            st.caption(f"{plural(s.historias, 'história', 'histórias')} · {plural(s.pontos, 'ponto', 'pontos')}")
            if st.button("Abrir", key=f"painel_abrir_{s.id}"):
                st.session_state[navegacao.BACKLOG_ABERTO] = s.id
                st.rerun()


# ---------- diálogo de destino (Q-28) ----------

def _rotulo_destino(d: BacklogDados) -> str:
    resumo = plural(d.historias, "história", "histórias")
    if d.e_product:
        return f"{d.nome} · {resumo}"
    return f"{d.nome} · {ESTADOS.get(d.estado or '', '')} · {resumo}"


def _dialogo_mover(usuario_id: int, origem: BacklogDados, backlogs_do_projeto: list[BacklogDados],
                   selecionadas: list[HistoriaDados]) -> None:
    """Escolhe o destino e confirma. `backlogs_do_projeto` traz product e sprints do projeto."""
    outros = [d for d in backlogs_do_projeto if d.id != origem.id]
    abertos = [d for d in outros if not d.somente_leitura]
    encerrados = [d for d in outros if d.somente_leitura]
    ids = [h.id for h in selecionadas]

    def corpo() -> None:
        st.caption(", ".join(h.codigo for h in selecionadas))
        if not abertos:
            st.warning("Não há outro backlog que possa receber estas histórias. "
                       "Crie um sprint backlog para movê-las.")
            if st.button("Fechar", key=f"btn_fechar_mover_{origem.id}"):
                st.rerun()
            return
        destino_id = st.radio(
            "Mover para", [d.id for d in abertos],
            format_func=lambda i: _rotulo_destino(next(d for d in abertos if d.id == i)),
            key=f"mover_destino_{origem.id}",
        )
        for d in encerrados:
            st.caption(f"🔒 {d.nome} · Encerrado (somente leitura): não recebe histórias")
        st.info("Mover não apaga nada: os critérios de aceitação, os pontos, a etiqueta MoSCoW, "
                "a nota RICE e os vínculos com épicos acompanham a história.")
        if st.button("Mover histórias", type="primary", key=f"btn_confirmar_mover_{origem.id}"):
            try:
                resultado = backlogs.mover_historias(usuario_id, ids, destino_id)
            except ErroDeValidacao as erro:
                st.error(" ".join(erro.erros.values()))
                return
            except (SprintEncerrado, HistoriaNaoEncontrada, BacklogNaoEncontrado) as erro:
                st.error(str(erro))
                return
            mensagem = (
                f"{plural(len(resultado.movidas), 'história movida', 'histórias movidas')} "
                f"para {resultado.destino.nome}. "
                f"Agora ele tem {plural(resultado.destino.historias, 'história', 'histórias')}."
            )
            if resultado.ja_no_destino:
                mensagem += f" ({', '.join(resultado.ja_no_destino)} já estava lá.)"
            st.session_state[navegacao.AVISO_BACKLOG] = mensagem
            _limpar_selecao(origem.id)
            st.rerun()
        if st.button("Cancelar", key=f"btn_cancelar_mover_{origem.id}"):
            st.rerun()

    st.dialog(f"Mover {plural(len(selecionadas), 'história', 'histórias')}")(corpo)()


# ---------- ponto de entrada ----------

def renderizar(usuario_id: int, b: BacklogDados, conjunto: BacklogsDoProjeto) -> None:
    """Histórias do backlog aberto. No product backlog, o painel de sprints fica à direita."""
    if b.historias == 0:
        st.caption("Nenhuma história neste backlog.")
        if b.e_product:
            _painel_sprints(conjunto)
        return
    if b.e_product:
        principal, lateral = st.columns([3, 1.4])
        with principal:
            _lista(usuario_id, b, conjunto)
        with lateral:
            _painel_sprints(conjunto)
    else:
        _lista(usuario_id, b, conjunto)
