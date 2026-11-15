"""Histórias de usuário (Storyboard 3: Q-14, Q-17 e Q-18).

Uma única página: a lista de histórias do projeto é a visão inicial (Q-14) e, ao abrir uma
história, a mesma página mostra o detalhe (Q-18, `historia_aberta` em st.session_state) com
os atributos de priorização sempre visíveis e as abas de critérios e detalhes. Criar, editar,
vincular a épicos e excluir usam diálogos; o retorno de sucesso é um toast na tela seguinte.

Ficam de fora o histórico e os anexos da história (abas do wireframe), que o sistema ainda não
registra, e a barra de progresso dos épicos: a história não tem estado de conclusão no modelo.
"""
import streamlit as st

from sgr.services import backlogs, epicos, historias
from sgr.services.historia_service import STORY_POINTS, HistoriaDados, HistoriaNaoEncontrada
from sgr.ui import criterios as ui_criterios
from sgr.ui import historias_form, navegacao
from sgr.ui.formatos import MOSCOW_NOMES, nota, plural
from sgr.ui.seletor import escolher_projeto
from sgr.ui.sessao import exigir_login

_ABERTA = navegacao.HISTORIA_ABERTA


def _exibir_aviso() -> None:
    mensagem = st.session_state.pop(navegacao.AVISO_HISTORIA, None)
    if mensagem:
        st.toast(mensagem, icon="✅")


def _chip_epicos(h: HistoriaDados) -> str:
    return " ".join(f"`{e.nome}`" for e in h.epicos) if h.epicos else "*sem épico*"  # pendência visível


def _resumo(h: HistoriaDados) -> str:
    pontos = f"{h.story_points} pts" if h.story_points is not None else "sem estimativa"
    rice = f"RICE {nota(h.rice)}" if h.rice is not None else "RICE —"
    return f"{pontos} · {h.moscow} · {rice}"


# ---------- lista (Q-14) ----------

def _limpar_filtros() -> None:
    for chave in ("flt_hist_epico", "flt_hist_moscow", "flt_hist_pontos"):
        st.session_state.pop(chave, None)


def _filtros(usuario_id: int, projeto_id: int):
    nomes = {e.id: e.nome for e in epicos.listar(usuario_id, projeto_id)}
    c1, c2, c3, c4 = st.columns([3, 3, 3, 2], vertical_alignment="bottom")
    epico_id = c1.selectbox("Épico", [None, *nomes], key="flt_hist_epico",
                            format_func=lambda v: "Todos" if v is None else nomes[v])
    moscow = c2.selectbox("MoSCoW", [None, *MOSCOW_NOMES], key="flt_hist_moscow",
                          format_func=lambda v: "Todas" if v is None else f"{v} · {MOSCOW_NOMES[v]}")
    pontos = c3.selectbox("Pontos", [None, *STORY_POINTS], key="flt_hist_pontos",
                          format_func=lambda v: "Qualquer" if v is None else str(v))
    c4.button("Limpar filtros", key="btn_limpar_filtros_historias", on_click=_limpar_filtros)
    return epico_id, moscow, pontos


def _lista(usuario_id: int, projeto_id: int, projeto_nome: str) -> None:
    tem_product = backlogs.listar(usuario_id, projeto_id).product is not None
    nova, epico = st.columns([2, 2])
    if nova.button("+ Nova história", type="primary", key="btn_nova_historia", disabled=not tem_product):
        historias_form.dialogo_historia(usuario_id, projeto_id)
    if epico.button("Épicos", key="btn_ir_epicos", disabled=not navegacao.disponivel("epicos")):
        navegacao.ir_para("epicos")
    if not tem_product:
        st.info("Este projeto ainda não tem product backlog. Crie o product backlog na página "
                "Backlogs para cadastrar histórias.")
        return

    epico_id, moscow, pontos = _filtros(usuario_id, projeto_id)
    lista = historias.listar(usuario_id, projeto_id, epico_id=epico_id, moscow=moscow)
    if pontos is not None:
        lista = [h for h in lista if h.story_points == pontos]
    if not lista:
        st.caption("Nenhuma história com esses filtros." if (epico_id or moscow or pontos is not None)
                   else f"{projeto_nome} ainda não tem histórias. Crie a primeira.")
    for h in lista:
        with st.container(border=True):
            corpo, abrir = st.columns([9, 2], vertical_alignment="center")
            corpo.markdown(f"**{h.codigo}** · {_chip_epicos(h)}")
            corpo.markdown(h.frase)
            corpo.caption(f"{_resumo(h)} · {h.backlog_nome}")
            if abrir.button("Abrir", key=f"btn_abrir_historia_{h.id}"):
                st.session_state[_ABERTA] = h.id
                st.rerun()


# ---------- detalhe (Q-18) ----------

def _detalhe(usuario_id: int, historia_id: int) -> None:
    try:
        h = historias.obter(usuario_id, historia_id)
    except HistoriaNaoEncontrada:
        st.session_state.pop(_ABERTA, None)
        st.rerun()
        return

    if st.button("← Histórias", key="btn_voltar_historias"):
        st.session_state.pop(_ABERTA, None)
        st.rerun()
    topo, editar, excluir = st.columns([6, 2, 2], vertical_alignment="center")
    topo.title(h.codigo)
    if editar.button("Editar", key="btn_editar_historia"):
        historias_form.dialogo_historia(usuario_id, h.projeto_id, h)
    if excluir.button("🗑 Excluir", key="btn_excluir_historia"):
        historias_form.dialogo_exclusao(usuario_id, h)
    st.markdown(f"#### {h.frase}")
    st.caption(f"{h.backlog_nome}")

    # Os quatro atributos de priorização ficam visíveis em qualquer aba.
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Pontos", h.story_points if h.story_points is not None else "—")
    m2.metric("MoSCoW", h.moscow)
    m3.metric("RICE", nota(h.rice) if h.rice is not None else "—")
    m4.metric("Épicos", len(h.epicos))

    aba_criterios, aba_detalhes = st.tabs(["Critérios de aceitação", "Detalhes"])
    with aba_criterios:
        ui_criterios.secao(usuario_id, h)
    with aba_detalhes:
        st.markdown(f"**Épicos:** {_chip_epicos(h)}")
        if st.button("Vincular a épicos", key="btn_vincular_epicos"):
            historias_form.dialogo_epicos(usuario_id, h)
        st.markdown(f"**Papel:** {h.papel}")
        st.markdown(f"**Ação:** {h.acao}")
        st.markdown(f"**Benefício:** {h.beneficio}")
        st.markdown(f"**MoSCoW:** {MOSCOW_NOMES[h.moscow]}")
        if h.rice is None:
            st.caption("RICE ainda não definido para esta história.")
        else:
            st.caption(f"RICE: Reach {h.rice_reach} · Impact {nota(h.rice_impact)} · "
                       f"Confidence {h.rice_confidence}% · Effort {h.rice_effort}")
        st.caption(f"{plural(h.criterios_total, 'critério de aceitação', 'critérios de aceitação')}")

    # Encadeamentos: "Salvar e adicionar critérios" (Q-15) e "Salvar e adicionar outro" (Q-19).
    if st.session_state.pop(navegacao.CRITERIO_REABRIR, None) == h.id:
        ui_criterios.dialogo_criterio(usuario_id, h)


def pagina_historias() -> None:
    usuario = exigir_login()
    _exibir_aviso()
    st.title("Histórias")
    escolha = escolher_projeto(usuario.id, "seletor_projeto_historias", "as histórias")
    if escolha is None:
        return
    projeto_id, projeto_nome = escolha
    historia_id = st.session_state.get(_ABERTA)
    if historia_id is None:
        _lista(usuario.id, projeto_id, projeto_nome)
    else:
        _detalhe(usuario.id, historia_id)
