"""Priorização do backlog (Storyboard 5: Q-32, Q-36 e Q-40; os diálogos ficam em priorizacao_form).

Uma tabela com as três dimensões lado a lado (story points, MoSCoW e RICE), filtros, ordenação
derivada do critério escolhido e, opcionalmente, o agrupamento por MoSCoW com a soma de pontos
por faixa. Não há arrastar nem posição manual: a ordem sempre vem do critério. Abaixo da tabela,
a matriz valor × esforço (somente leitura) resume as histórias que têm RICE.

Cada linha tem uma caixa de seleção; com histórias marcadas, a barra acima da tabela habilita
"Mover para..." (Storyboard 4) e "Aplicar pontos..." (edição em lote, Q-34). Mover é por seleção e
botão, nunca por arraste, e a seleção pode vir de backlogs diferentes.
"""
from collections import Counter
from decimal import Decimal

import streamlit as st

from sgr.services import backlogs, epicos, historias
from sgr.services.historia_service import STORY_POINTS, HistoriaDados
from sgr.ui import navegacao, priorizacao_form
from sgr.ui.formatos import MOSCOW_NOMES, nota, plural
from sgr.ui.seletor import escolher_projeto
from sgr.ui.sessao import exigir_login

_ORDENS = {
    "rice": "RICE (maior primeiro)",
    "pontos": "Pontos (maior primeiro)",
    "moscow": "MoSCoW (M a W)",
    "criacao": "Data de criação",
    "titulo": "Título (A–Z)",
}
_FILTROS = ("flt_prio_epico", "flt_prio_moscow", "flt_prio_pontos", "flt_prio_rice")
_RICE_OPCOES = {None: "Qualquer", True: "Com RICE", False: "Sem RICE"}


def _exibir_aviso() -> None:
    mensagem = st.session_state.pop(navegacao.AVISO_PRIORIZACAO, None)
    if mensagem:
        st.toast(mensagem, icon="✅")


# ---------- filtros e ordenação (Q-32) ----------

def _limpar_filtros() -> None:
    for chave in _FILTROS:
        st.session_state.pop(chave, None)


def _filtros(usuario_id: int, projeto_id: int):
    nomes = {e.id: e.nome for e in epicos.listar(usuario_id, projeto_id)}
    c1, c2, c3, c4, c5 = st.columns([3, 3, 2, 2, 2], vertical_alignment="bottom")
    epico_id = c1.selectbox("Épico", [None, *nomes], key="flt_prio_epico",
                            format_func=lambda v: "Todos" if v is None else nomes[v])
    moscow = c2.multiselect("MoSCoW", list(MOSCOW_NOMES), key="flt_prio_moscow", placeholder="Todas",
                            format_func=lambda v: f"{v} · {MOSCOW_NOMES[v]}")
    pontos = c3.selectbox("Pontos", [None, *STORY_POINTS], key="flt_prio_pontos",
                          format_func=lambda v: "Qualquer" if v is None else str(v))
    rice = c4.selectbox("RICE", list(_RICE_OPCOES), key="flt_prio_rice", format_func=_RICE_OPCOES.get)
    c5.button("Limpar filtros", key="btn_limpar_filtros_priorizacao", on_click=_limpar_filtros)
    return epico_id, tuple(moscow), pontos, rice


def _filtrar(lista: list[HistoriaDados], epico_id, pontos, rice) -> list[HistoriaDados]:
    """Filtros que não são de MoSCoW (o resumo por faixa precisa das histórias fora do filtro)."""
    if epico_id is not None:
        lista = [h for h in lista if any(e.id == epico_id for e in h.epicos)]
    if pontos is not None:
        lista = [h for h in lista if h.story_points == pontos]
    if rice is not None:
        lista = [h for h in lista if (h.rice is not None) == rice]
    return lista


def _ordenar(lista: list[HistoriaDados], criterio: str, inverter: bool) -> list[HistoriaDados]:
    """Ordem derivada do critério. Empates seguem a ordem de criação; sem valor fica sempre no fim."""
    base = sorted(lista, key=lambda h: h.id)
    if criterio in ("rice", "pontos"):
        valor = (lambda h: h.rice) if criterio == "rice" else (lambda h: h.story_points)
        com = sorted((h for h in base if valor(h) is not None), key=valor, reverse=not inverter)
        return com + [h for h in base if valor(h) is None]
    if criterio == "moscow":
        return sorted(base, key=lambda h: list(MOSCOW_NOMES).index(h.moscow), reverse=inverter)
    if criterio == "titulo":
        return sorted(base, key=lambda h: h.frase.casefold(), reverse=inverter)
    return base[::-1] if inverter else base


def _pontos(lista: list[HistoriaDados]) -> int:
    return sum(h.story_points or 0 for h in lista)


# ---------- seleção para mover e edição em lote ----------

def _barra_selecao(usuario_id: int, projeto_id: int, selecionadas: list[HistoriaDados]) -> None:
    with st.container(border=True):
        texto, mover, lote, limpar = st.columns([5, 2, 3, 2], vertical_alignment="center")
        if selecionadas:
            texto.markdown(f"**{plural(len(selecionadas), 'história selecionada', 'histórias selecionadas')}**")
        else:
            texto.caption("Marque a caixa de seleção de uma ou mais histórias para habilitar.")
        vazia = not selecionadas
        if mover.button("Mover para...", type="primary", key="btn_mover_prio", disabled=vazia):
            conjunto = backlogs.listar(usuario_id, projeto_id)
            destinos = ([conjunto.product] if conjunto.product else []) + conjunto.sprints
            priorizacao_form.dialogo_mover(usuario_id, selecionadas, destinos)
        if lote.button("Aplicar pontos...", key="btn_lote_prio", disabled=vazia):
            priorizacao_form.dialogo_pontos_em_lote(usuario_id, selecionadas)
        limpar.button("Limpar seleção", key="btn_limpar_selecao_prio", disabled=vazia,
                      on_click=priorizacao_form.limpar_selecao)


# ---------- tabela ----------

_LARGURAS = [0.7, 6, 2, 1, 1, 1.4, 1]


def _cabecalho() -> None:
    cols = st.columns(_LARGURAS)
    for col, titulo in zip(cols, ["", "História", "Épico", "Pontos", "MoSCoW", "RICE ƒ", ""]):
        col.markdown(f"**{titulo}**")


def _linha(usuario_id: int, h: HistoriaDados, todas: list[HistoriaDados], contagens: Counter,
           alterada: int | None) -> None:
    with st.container(border=True):
        c_sel, c_hist, c_epico, c_pts, c_moscow, c_rice, c_mais = st.columns(_LARGURAS, vertical_alignment="center")
        c_sel.checkbox(f"Selecionar {h.codigo}", key=priorizacao_form.chave_selecao(h.id), label_visibility="collapsed")
        c_hist.markdown(f"**{h.codigo}** · {h.frase}" + (" · *(alterada)*" if h.id == alterada else ""))
        c_epico.caption(", ".join(e.nome for e in h.epicos) or "—")
        c_pts.markdown(str(h.story_points) if h.story_points is not None else "—")
        c_moscow.markdown(h.moscow)
        c_rice.markdown(nota(h.rice) if h.rice is not None else "—")
        with c_mais.popover("⋯"):
            if st.button("Estimar pontos", key=f"btn_pontos_{h.id}", use_container_width=True):
                priorizacao_form.dialogo_pontos(usuario_id, h, priorizacao_form.sugestao_pontos(h, todas))
            if st.button("Etiqueta MoSCoW", key=f"btn_moscow_{h.id}", use_container_width=True):
                priorizacao_form.dialogo_moscow(usuario_id, h, dict(contagens))
            if st.button("Critério RICE", key=f"btn_rice_{h.id}", use_container_width=True):
                priorizacao_form.dialogo_rice(usuario_id, h)


def _tabela(usuario_id: int, lista: list[HistoriaDados], todas: list[HistoriaDados], contagens: Counter,
            alterada: int | None) -> None:
    _cabecalho()
    for h in lista:
        _linha(usuario_id, h, todas, contagens, alterada)


# ---------- agrupamento por MoSCoW (Q-36) ----------

def _agrupada(usuario_id: int, lista: list[HistoriaDados], base: list[HistoriaDados], moscow: tuple[str, ...],
              todas: list[HistoriaDados], contagens: Counter, alterada: int | None) -> None:
    for letra, nome in MOSCOW_NOMES.items():
        grupo = [h for h in lista if h.moscow == letra]
        if not grupo:
            continue
        st.markdown(f"#### {nome} ({plural(len(grupo), 'história', 'histórias')})")
        _tabela(usuario_id, grupo, todas, contagens, alterada)
    st.markdown("**Resumo por faixa**")
    for letra in MOSCOW_NOMES:
        faixa = [h for h in base if h.moscow == letra]
        fora = bool(moscow) and letra not in moscow
        st.caption(f"{letra}: {len(faixa)} · {_pontos(faixa)} pts" + (" — fora do filtro" if fora else ""))


# ---------- matriz valor × esforço (Q-40) ----------

def _valor(h: HistoriaDados) -> Decimal:
    return Decimal(h.rice_reach) * h.rice_impact * Decimal(h.rice_confidence) / 100


def _quadrantes(lista: list[HistoriaDados]) -> dict[str, list[str]]:
    """Códigos das histórias com RICE em cada quadrante; o corte é a média de valor e de esforço."""
    com = [h for h in lista if h.rice is not None]
    quadrantes: dict[str, list[str]] = {"fazer agora": [], "avaliar com calma": [], "ganho rápido": [], "descartar": []}
    if not com:
        return quadrantes
    media_valor = sum(_valor(h) for h in com) / len(com)
    media_esforco = Decimal(sum(h.rice_effort for h in com)) / len(com)
    for h in com:
        alto, leve = _valor(h) >= media_valor, h.rice_effort <= media_esforco
        nome = ("fazer agora" if leve else "avaliar com calma") if alto else ("ganho rápido" if leve else "descartar")
        quadrantes[nome].append(h.codigo)
    return quadrantes


def _matriz(lista: list[HistoriaDados]) -> None:
    st.markdown("**Valor × esforço**")
    if not any(h.rice is not None for h in lista):
        st.caption("Nenhuma história com RICE para comparar.")
        return
    quadrantes = _quadrantes(lista)
    topo, baixo = st.columns(2), st.columns(2)
    for coluna, nome in zip([*topo, *baixo], quadrantes):
        with coluna.container(border=True):
            st.markdown(f"**{nome}**")
            st.caption(", ".join(quadrantes[nome]) or "—")
    st.caption("Em cima: valor (R × I × C) a partir da média. À esquerda: esforço até a média. "
               "Posição derivada das entradas: não é possível arrastar para mudar o valor.")


def _corte(lista: list[HistoriaDados]) -> None:
    notas = [h.rice for h in lista if h.rice is not None]
    if len(notas) < 2:
        return
    media = sum(notas) / len(notas)
    st.caption(f"corte sugerido: {plural(sum(1 for n in notas if n > media), 'item', 'itens')} acima da média")


# ---------- página ----------

def pagina_priorizacao() -> None:
    usuario = exigir_login()
    _exibir_aviso()
    st.title("Priorização")
    escolha = escolher_projeto(usuario.id, "seletor_projeto_priorizacao", "a priorização")
    if escolha is None:
        return
    projeto_id, projeto_nome = escolha
    alterada = st.session_state.pop(navegacao.HISTORIA_ALTERADA, None)

    todas = historias.listar(usuario.id, projeto_id)
    contagens = Counter(h.moscow for h in todas)
    epico_id, moscow, pontos, rice = _filtros(usuario.id, projeto_id)
    base = _filtrar(todas, epico_id, pontos, rice)
    lista = [h for h in base if not moscow or h.moscow in moscow]

    topo, c_ordem, c_inverter = st.columns([4, 4, 2], vertical_alignment="bottom")
    topo.markdown(f"**{plural(len(lista), 'história', 'histórias')} · {plural(_pontos(lista), 'ponto', 'pontos')}**")
    criterio = c_ordem.selectbox("Ordenar por", list(_ORDENS), key="flt_prio_ordem", format_func=_ORDENS.get)
    inverter = c_inverter.toggle("Inverter ordem", key="flt_prio_inverter")
    agrupar = st.toggle("Agrupar por MoSCoW", key="flt_prio_agrupar")
    st.caption("A ordem é derivada do critério escolhido: não há posição manual nem arraste.")

    if not lista:
        st.caption("Nenhuma história com esses filtros." if (todas and (base != todas or moscow))
                   else f"{projeto_nome} ainda não tem histórias. Cadastre-as na página Histórias.")
        return
    ordenada = _ordenar(lista, criterio, inverter)
    selecionadas = [h for h in ordenada if st.session_state.get(priorizacao_form.chave_selecao(h.id))]
    _barra_selecao(usuario.id, projeto_id, selecionadas)
    if agrupar:
        _agrupada(usuario.id, ordenada, base, moscow, todas, contagens, alterada)
    else:
        _tabela(usuario.id, ordenada, todas, contagens, alterada)
    if criterio == "rice":
        _corte(ordenada)
    _matriz(ordenada)
