"""Diálogos de priorização (Storyboard 5: Q-33 a Q-35 e Q-37 a Q-39).

- Q-33 story points: paleta fechada de valores, com porte e sugestão pelo histórico do épico.
- Q-34/Q-38 valores inválidos: os controles só oferecem valores do domínio; se o serviço ainda
  recusar algum, a mensagem (que lista os valores aceitos) aparece no próprio campo.
- Q-35 MoSCoW: letra, nome, descrição e quantas histórias do projeto já têm cada etiqueta.
- Q-34 (C) edição em lote: a mesma paleta de pontos aplicada às histórias selecionadas, tudo ou nada.
- Q-37/Q-39 RICE: quatro entradas com domínio fechado; a nota é calculada na hora (nunca digitada),
  com a conta à vista e a variação em relação à nota gravada.
- Seleção para mover (Storyboard 4, Q-29): destino por seleção e botão, como na página Backlogs.
"""
from decimal import Decimal

import streamlit as st

from sgr.services import backlogs, priorizacao
from sgr.services.auth_service import ErroDeValidacao
from sgr.services.backlog_service import BacklogDados, BacklogNaoEncontrado, SprintEncerrado
from sgr.services.historia_service import STORY_POINTS, HistoriaDados, HistoriaNaoEncontrada
from sgr.services.rice import CONFIANCAS, ESFORCOS, IMPACTOS
from sgr.ui import navegacao
from sgr.ui.backlog_historias import _rotulo_destino
from sgr.ui.formatos import MOSCOW_NOMES, nota, plural

PORTES = {0: "", 1: "muito pequeno", 2: "pequeno", 3: "pequeno", 5: "médio", 8: "médio",
          13: "grande", 21: "muito grande", 34: "épico", 55: "épico"}
MOSCOW_DESCRICOES = {
    "M": "obrigatório neste escopo",
    "S": "importante, mas não bloqueia",
    "C": "desejável, se houver folga",
    "W": "fora deste escopo, registrado para depois",
}
IMPACTO_NOMES = {Decimal("3"): "massivo", Decimal("2"): "alto", Decimal("1"): "médio",
                 Decimal("0.5"): "baixo", Decimal("0.25"): "mínimo"}
CONFIANCA_NOMES = {100: "alta", 80: "média", 50: "baixa"}


def _fechar(chave: str) -> None:
    if st.button("Fechar", key=chave):
        st.rerun()


def _concluir(mensagem: str, alterada: int | None = None) -> None:
    st.session_state[navegacao.AVISO_PRIORIZACAO] = mensagem
    if alterada is not None:
        st.session_state[navegacao.HISTORIA_ALTERADA] = alterada
    st.rerun()


# ---------- seleção ----------

def chave_selecao(historia_id: int) -> str:
    """Chave da caixa de seleção. A geração muda ao limpar: caixas novas, desmarcadas."""
    geracao = st.session_state.get(navegacao.GERACAO_SELECAO_PRIORIZACAO, 0)
    return f"sel_prio_{geracao}_{historia_id}"


def limpar_selecao() -> None:
    st.session_state[navegacao.GERACAO_SELECAO_PRIORIZACAO] = (
        st.session_state.get(navegacao.GERACAO_SELECAO_PRIORIZACAO, 0) + 1
    )


# ---------- Q-33: story points ----------

def sugestao_pontos(h: HistoriaDados, todas: list[HistoriaDados]) -> str | None:
    """Média dos story points das últimas 3 histórias estimadas do primeiro épico da história."""
    if not h.epicos:
        return None
    epico = h.epicos[0]
    irmas = sorted((o for o in todas if o.id != h.id and o.story_points is not None
                    and any(e.id == epico.id for e in o.epicos)), key=lambda o: o.id)[-3:]
    if not irmas:
        return None
    media = sum(o.story_points for o in irmas) / len(irmas)
    proximo = min(STORY_POINTS, key=lambda v: (abs(v - media), v))
    base = f"a média das últimas {len(irmas)} histórias estimadas do épico {epico.nome}"
    if media == proximo:
        return f"Sugestão do sistema: {base} é {proximo} pontos."
    return (f"Sugestão do sistema: {base} é {str(round(media, 1)).replace('.', ',')} pontos "
            f"(valor mais próximo da escala: {proximo}).")


def dialogo_pontos(usuario_id: int, h: HistoriaDados, sugestao: str | None = None) -> None:
    p = f"pt{h.id}_"

    def corpo() -> None:
        st.caption(h.frase)
        st.radio("Story points ★", list(STORY_POINTS), key=p + "valor", horizontal=True,
                 index=STORY_POINTS.index(h.story_points) if h.story_points is not None else None,
                 captions=[PORTES[v] for v in STORY_POINTS])
        st.caption("A escala é fixa. Não é possível informar valores como 4 ou 7.")
        erro = st.empty()
        if sugestao:
            st.info(sugestao)
        c1, c2 = st.columns(2)
        if c1.button("Cancelar", key=p + "cancelar"):
            st.rerun()
        if not c2.button("Salvar estimativa", type="primary", key=p + "salvar"):
            return
        valor = st.session_state.get(p + "valor")
        if valor is None:  # None no serviço remove a estimativa; aqui a escolha é obrigatória
            erro.error("Selecione um valor da escala: " + ", ".join(str(v) for v in STORY_POINTS) + ".")
            return
        try:
            salva = priorizacao.definir_story_points(usuario_id, h.id, valor)
        except ErroDeValidacao as e:
            erro.error(e.erros.get("story_points", "Selecione um valor da escala."))
            return
        except HistoriaNaoEncontrada as e:
            st.error(str(e))
            return
        _concluir(f"✓ Estimativa de {h.codigo} salva: {plural(salva.story_points, 'ponto', 'pontos')}.")

    st.dialog(f"Estimar história {h.codigo}")(corpo)()


# ---------- Q-35: MoSCoW ----------

def dialogo_moscow(usuario_id: int, h: HistoriaDados, contagens: dict[str, int]) -> None:
    p = f"ms{h.id}_"
    letras = list(MOSCOW_NOMES)

    def corpo() -> None:
        st.caption(h.frase)
        st.radio("Prioridade MoSCoW ★", letras, key=p + "valor", index=letras.index(h.moscow),
                 format_func=lambda v: f"{v} · {MOSCOW_NOMES[v]}",
                 captions=[f"{MOSCOW_DESCRICOES[v]} · {plural(contagens.get(v, 0), 'história', 'histórias')}"
                           for v in letras])
        st.caption("A etiqueta é obrigatória. Toda história precisa de uma das quatro.")
        erro = st.empty()
        c1, c2 = st.columns(2)
        if c1.button("Cancelar", key=p + "cancelar"):
            st.rerun()
        if not c2.button("Salvar prioridade", type="primary", key=p + "salvar"):
            return
        try:
            salva = priorizacao.definir_moscow(usuario_id, h.id, st.session_state.get(p + "valor"))
        except ErroDeValidacao as e:
            erro.error(e.erros.get("moscow", "Informe a etiqueta MoSCoW."))
            return
        except HistoriaNaoEncontrada as e:
            st.error(str(e))
            return
        _concluir(f"✓ Prioridade de {h.codigo}: {salva.moscow} · {MOSCOW_NOMES[salva.moscow]}.")

    st.dialog(f"Prioridade MoSCoW — {h.codigo}")(corpo)()


# ---------- Q-37 a Q-39: RICE ----------

def _seta(antes: Decimal, agora: Decimal) -> str:
    return "↑" if agora > antes else "↓" if agora < antes else "="


def dialogo_rice(usuario_id: int, h: HistoriaDados) -> None:
    p = f"rc{h.id}_"

    def corpo() -> None:
        tem = h.rice is not None
        st.caption(f"{h.frase} · {h.codigo}")
        reach = st.number_input("Reach ★ — número de usuários", min_value=0, step=1, key=p + "reach",
                                value=h.rice_reach if tem else None, placeholder="ex.: 100",
                                help="Quantos usuários são alcançados no período.")
        erro_reach = st.empty()
        impacto = st.radio("Impact ★", list(IMPACTOS), key=p + "impact", horizontal=True,
                           index=IMPACTOS.index(h.rice_impact) if tem else None,
                           format_func=lambda v: f"{nota(v)} · {IMPACTO_NOMES[v]}")
        erro_impacto = st.empty()
        confianca = st.radio("Confidence ★", list(CONFIANCAS), key=p + "confidence", horizontal=True,
                             index=CONFIANCAS.index(h.rice_confidence) if tem else None,
                             format_func=lambda v: f"{v}% · {CONFIANCA_NOMES[v]}")
        erro_confianca = st.empty()
        esforco = st.radio("Effort ★ — em pontos de história", list(ESFORCOS), key=p + "effort",
                           horizontal=True, index=ESFORCOS.index(h.rice_effort) if tem else None)
        st.caption("Mesma escala dos story points. O zero não é aceito: a divisão da fórmula seria impossível.")
        erro_esforco = st.empty()

        novo = None
        if None not in (reach, impacto, confianca, esforco):
            try:
                novo = priorizacao.calcular_rice(reach, impacto, confianca, esforco)
            except ErroDeValidacao:
                novo = None
        st.markdown("**Pontuação RICE** ƒ")
        if novo is None:
            st.markdown("### —")
            st.caption("aguardando valores válidos")
        else:
            st.markdown(f"### {nota(novo)}")
            st.caption(f"({reach} × {nota(impacto)} × {confianca}%) / {esforco} = {nota(novo)}")
            if tem and novo != h.rice:
                st.caption(f"antes {nota(h.rice)} · agora {nota(novo)} {_seta(h.rice, novo)}")
        st.caption("Calculado pelo sistema · não editável")

        c1, c2 = st.columns(2)
        if c1.button("Cancelar", key=p + "cancelar"):
            st.rerun()
        if not c2.button("Salvar critério RICE", type="primary", key=p + "salvar"):
            return
        try:
            salva = priorizacao.definir_rice(usuario_id, h.id, reach, impacto, confianca, esforco)
        except ErroDeValidacao as e:  # nada é apagado: a pessoa corrige só o campo apontado
            destinos = {"rice_reach": erro_reach, "rice_impact": erro_impacto,
                        "rice_confidence": erro_confianca, "rice_effort": erro_esforco}
            for campo, mensagem in e.erros.items():
                destinos.get(campo, erro_reach).error(mensagem)
            return
        except HistoriaNaoEncontrada as e:
            st.error(str(e))
            return
        if tem and salva.rice != h.rice:
            _concluir(f"✓ RICE de {h.codigo}: {nota(h.rice)} → {nota(salva.rice)} {_seta(h.rice, salva.rice)}",
                      alterada=h.id)
        _concluir(f"✓ RICE de {h.codigo}: {nota(salva.rice)}.", alterada=None if tem else h.id)

    st.dialog(f"Critério RICE — {h.codigo}")(corpo)()


# ---------- Q-34 (C): story points em lote ----------

def dialogo_pontos_em_lote(usuario_id: int, selecionadas: list[HistoriaDados]) -> None:
    p = "ptlote_"
    n = len(selecionadas)

    def corpo() -> None:
        st.caption(", ".join(h.codigo for h in selecionadas))
        st.radio("Story points ★", list(STORY_POINTS), key=p + "valor", horizontal=True, index=None,
                 captions=[PORTES[v] for v in STORY_POINTS])
        st.caption("Selecione um valor da lista para aplicar em lote. A escala é fixa.")
        erro = st.empty()
        c1, c2 = st.columns(2)
        if c1.button("Cancelar", key=p + "cancelar"):
            st.rerun()
        if not c2.button(f"Aplicar pontos a {plural(n, 'história', 'histórias')}", type="primary", key=p + "aplicar"):
            return
        valor = st.session_state.get(p + "valor")
        if valor is None:
            erro.error("Selecione um valor da escala: " + ", ".join(str(v) for v in STORY_POINTS) + ".")
            return
        try:
            priorizacao.definir_story_points_em_lote(usuario_id, [h.id for h in selecionadas], valor)
        except ErroDeValidacao as e:
            erro.error(" ".join(e.erros.values()))
            return
        except HistoriaNaoEncontrada as e:  # nenhuma foi alterada
            st.error(str(e))
            return
        limpar_selecao()
        _concluir(f"✓ {plural(valor, 'ponto aplicado', 'pontos aplicados')} a {plural(n, 'história', 'histórias')}.")

    st.dialog(f"Aplicar pontos a {plural(n, 'história', 'histórias')}")(corpo)()


# ---------- Q-29: mover para outro backlog ----------

def dialogo_mover(usuario_id: int, selecionadas: list[HistoriaDados], destinos: list[BacklogDados]) -> None:
    """Escolhe o destino (product ou sprint aberto) e move a seleção, que pode vir de backlogs diferentes."""
    origens = {h.backlog_id for h in selecionadas}
    outros = [d for d in destinos if not (len(origens) == 1 and d.id in origens)]
    abertos = [d for d in outros if not d.somente_leitura]
    encerrados = [d for d in outros if d.somente_leitura]
    ids = [h.id for h in selecionadas]
    p = "mvprio_"

    def corpo() -> None:
        st.caption(", ".join(h.codigo for h in selecionadas))
        if not abertos:
            st.warning("Não há outro backlog que possa receber estas histórias. "
                       "Crie um sprint backlog para movê-las.")
            _fechar(p + "fechar")
            return
        destino_id = st.radio("Mover para", [d.id for d in abertos], key=p + "destino",
                              format_func=lambda i: _rotulo_destino(next(d for d in abertos if d.id == i)))
        for d in encerrados:
            st.caption(f"🔒 {d.nome} · Encerrado (somente leitura): não recebe histórias")
        st.info("Mover não apaga nada: os critérios de aceitação, os pontos, a etiqueta MoSCoW, "
                "a nota RICE e os vínculos com épicos acompanham a história.")
        c1, c2 = st.columns(2)
        if c1.button("Cancelar", key=p + "cancelar"):
            st.rerun()
        if not c2.button("Mover histórias", type="primary", key=p + "confirmar"):
            return
        try:
            resultado = backlogs.mover_historias(usuario_id, ids, destino_id)
        except ErroDeValidacao as e:
            st.error(" ".join(e.erros.values()))
            return
        except (SprintEncerrado, HistoriaNaoEncontrada, BacklogNaoEncontrado) as e:
            st.error(str(e))
            return
        mensagem = (f"✓ {plural(len(resultado.movidas), 'história movida', 'histórias movidas')} "
                    f"para {resultado.destino.nome}.")
        if resultado.ja_no_destino:
            mensagem += f" ({', '.join(resultado.ja_no_destino)} já estava lá.)"
        limpar_selecao()
        _concluir(mensagem)

    st.dialog(f"Mover {plural(len(selecionadas), 'história', 'histórias')}")(corpo)()
