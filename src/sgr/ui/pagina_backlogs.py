"""Backlogs (requisitos 5 e 6): product backlog (um por projeto) e sprint backlogs — Storyboard 3.

Cobre listar, criar, ver, editar e excluir. As histórias do backlog aberto e a movimentação
entre backlogs (requisito 8) ficam em backlog_historias.py. Criar, editar, excluir e mover usam
diálogos modais; o retorno de sucesso é um toast mostrado na tela seguinte.
"""
from datetime import date, timedelta

import streamlit as st

from sgr.services import backlogs, projetos
from sgr.services.auth_service import ErroDeValidacao
from sgr.services.backlog_service import (
    DESCRICAO_MAX,
    NOME_MAX,
    NOME_PADRAO_PRODUCT,
    BacklogDados,
    BacklogNaoEncontrado,
    ProductBacklogComHistorias,
    ProductBacklogJaExiste,
    SemProductBacklog,
)
from sgr.services.projeto_service import ProjetoNaoEncontrado
from sgr.ui import backlog_historias, navegacao
from sgr.ui.formatos import ESTADOS as _ESTADOS
from sgr.ui.formatos import data as _data
from sgr.ui.formatos import plural as _plural
from sgr.ui.sessao import exigir_login

_PROJETO = navegacao.PROJETO_DOS_BACKLOGS
_ABERTO = navegacao.BACKLOG_ABERTO
_AVISO = navegacao.AVISO_BACKLOG
_EXPLICACAO_BLOQUEIO = "Este projeto já tem um product backlog. Para outro, crie um novo projeto."


def _periodo(b: BacklogDados) -> str:
    return f"{_data(b.data_inicio)} a {_data(b.data_fim)}"


def _resumo(b: BacklogDados) -> str:
    return f"{_plural(b.historias, 'história', 'histórias')} · {_plural(b.pontos, 'ponto', 'pontos')}"


def _avisar(mensagem: str) -> None:
    """Guarda o aviso para o toast da próxima execução (um st.rerun() logo depois o perderia)."""
    st.session_state[_AVISO] = mensagem


def _exibir_aviso() -> None:
    mensagem = st.session_state.pop(_AVISO, None)
    if mensagem:
        st.toast(mensagem, icon="✅")


# ---------- diálogos ----------

def _dialogo_product(usuario_id: int, projeto_id: int, projeto_nome: str, backlog: BacklogDados | None,
                     existente: BacklogDados | None = None) -> None:
    """Criar (backlog=None) ou editar o product backlog. `existente` é o já criado, se houver."""
    editando = backlog is not None

    if not editando and existente is not None:  # regra de cardinalidade: o aviso substitui o formulário
        def aviso() -> None:
            st.error(f"O projeto {projeto_nome} já possui o {existente.nome}. Cada projeto admite apenas um.")
            st.caption(_EXPLICACAO_BLOQUEIO)
            if st.button("Voltar aos backlogs", key="btn_voltar_aos_backlogs"):
                st.rerun()

        st.dialog("Não é possível criar outro product backlog")(aviso)()
        return

    sufixo = backlog.id if editando else "novo"

    def corpo() -> None:
        st.caption(f"Projeto: {projeto_nome} (somente leitura)")
        with st.form(f"form_product_{sufixo}", border=False):
            nome = st.text_input(
                "Nome *",
                value=backlog.nome if editando else NOME_PADRAO_PRODUCT,
                max_chars=NOME_MAX,
                key=f"product_nome_{sufixo}",
            )
            erro_nome = st.empty()
            descricao = st.text_area(
                "Descrição",
                value=(backlog.descricao or "") if editando else "",
                max_chars=DESCRICAO_MAX,
                placeholder="O que este backlog reúne?",
                key=f"product_descricao_{sufixo}",
            )
            erro_descricao = st.empty()
            if not editando:
                st.info(
                    "Cada projeto tem um único product backlog. Ele reúne todas as histórias do "
                    "produto e é o ponto de partida de todo sprint."
                )
            enviar = st.form_submit_button(
                "Salvar alterações" if editando else "Criar product backlog",
                type="primary",
                key=f"btn_salvar_product_{sufixo}",
            )
        if st.button("Cancelar", key=f"btn_cancelar_product_{sufixo}"):
            st.rerun()
        if not enviar:
            return
        try:
            if editando:
                backlogs.atualizar(usuario_id, backlog.id, nome, descricao)
                _avisar("Product backlog atualizado.")
            else:
                backlogs.criar_product(usuario_id, projeto_id, nome, descricao)
                _avisar("Product backlog criado.")
        except ErroDeValidacao as erro:
            if "nome" in erro.erros:
                erro_nome.error(erro.erros["nome"])
            if "descricao" in erro.erros:
                erro_descricao.error(erro.erros["descricao"])
            return
        except (ProductBacklogJaExiste, BacklogNaoEncontrado, ProjetoNaoEncontrado) as erro:
            st.error(str(erro))
            return
        st.rerun()

    st.dialog("Editar product backlog" if editando else "Novo product backlog")(corpo)()


def _dialogo_sprint(usuario_id: int, projeto_id: int, projeto_nome: str, backlog: BacklogDados | None) -> None:
    """Criar (backlog=None) ou editar um sprint backlog. O estado é somente leitura."""
    editando = backlog is not None
    sufixo = backlog.id if editando else "novo"
    hoje = date.today()
    sugestao = "" if editando else backlogs.sugerir_nome_sprint(usuario_id, projeto_id)

    def corpo() -> None:
        st.caption(f"Projeto: {projeto_nome} (somente leitura)")
        nome = st.text_input(
            "Nome *",
            value=backlog.nome if editando else sugestao,
            max_chars=NOME_MAX,
            key=f"sprint_nome_{sufixo}",
        )
        erro_nome = st.empty()
        col_inicio, col_fim = st.columns(2)
        inicio = col_inicio.date_input(
            "Início *",
            value=backlog.data_inicio if editando else hoje,
            format="DD/MM/YYYY",
            key=f"sprint_inicio_{sufixo}",
        )
        erro_inicio = col_inicio.empty()
        fim = col_fim.date_input(
            "Fim *",
            value=backlog.data_fim if editando else hoje + timedelta(days=13),
            format="DD/MM/YYYY",
            key=f"sprint_fim_{sufixo}",
        )
        erro_fim = col_fim.empty()
        if isinstance(inicio, date) and isinstance(fim, date) and fim > inicio:
            st.caption(f"Duração: {(fim - inicio).days + 1} dias")
        meta = st.text_area(
            "Meta do sprint",
            value=(backlog.descricao or "") if editando else "",
            max_chars=DESCRICAO_MAX,
            placeholder="O que queremos entregar neste ciclo?",
            key=f"sprint_meta_{sufixo}",
        )
        erro_meta = st.empty()
        if editando:
            st.text_input("Estado", value=_ESTADOS.get(backlog.estado or "", ""), disabled=True,
                          key=f"sprint_estado_{sufixo}")
            st.info("As histórias deste sprint não são afetadas pela alteração do nome ou do período.")
        enviar = st.button(
            "Salvar alterações" if editando else "Criar sprint",
            type="primary",
            key=f"btn_salvar_sprint_{sufixo}",
        )
        if st.button("Cancelar", key=f"btn_cancelar_sprint_{sufixo}"):
            st.rerun()
        if not enviar:
            return
        try:
            if editando:
                backlogs.atualizar(usuario_id, backlog.id, nome, meta, inicio, fim)
                _avisar("Sprint atualizado.")
            else:
                backlogs.criar_sprint(usuario_id, projeto_id, nome, inicio, fim, meta)
                _avisar("Sprint criado.")
        except ErroDeValidacao as erro:
            for campo, destino in (("nome", erro_nome), ("data_inicio", erro_inicio),
                                   ("data_fim", erro_fim), ("descricao", erro_meta)):
                if campo in erro.erros:
                    destino.error(erro.erros[campo])
            return
        except (BacklogNaoEncontrado, ProjetoNaoEncontrado) as erro:
            st.error(str(erro))
            return
        st.rerun()

    st.dialog("Editar sprint backlog" if editando else "Novo sprint backlog")(corpo)()


def _dialogo_exclusao(usuario_id: int, backlog: BacklogDados, tem_product: bool) -> None:
    """Exclusão com comportamento por tipo (quadro 9): sprint devolve histórias; product só vazio."""

    def excluir_e_avisar(mensagem: str) -> None:
        try:
            backlogs.excluir(usuario_id, backlog.id)
        except (ProductBacklogComHistorias, SemProductBacklog, BacklogNaoEncontrado) as erro:
            st.error(str(erro))
            return
        st.session_state.pop(_ABERTO, None)
        _avisar(mensagem)
        st.rerun()

    if backlog.e_product and backlog.historias:
        def bloqueio() -> None:
            st.error("Não é possível excluir o Product Backlog.")
            st.markdown(
                "- ele é obrigatório em todo projeto\n"
                f"- {_plural(backlog.historias, 'história depende', 'histórias dependem')} dele\n"
                "- todo projeto precisa de um product backlog para receber histórias"
            )
            if st.button("Entendi", key=f"btn_entendi_{backlog.id}"):
                st.rerun()

        st.dialog("Não é possível excluir o Product Backlog")(bloqueio)()
        return

    if backlog.e_product:
        def corpo_product() -> None:
            st.write("Este backlog não tem histórias e pode ser excluído.")
            if st.button("Excluir backlog", type="primary", key=f"btn_confirmar_exclusao_{backlog.id}"):
                excluir_e_avisar("Product backlog excluído.")
            if st.button("Cancelar", key=f"btn_cancelar_exclusao_{backlog.id}"):
                st.rerun()

        st.dialog("Excluir este product backlog?")(corpo_product)()
        return

    def corpo_sprint() -> None:
        n = backlog.historias
        if n:
            st.markdown(
                f"**{_plural(n, 'história será movida', 'histórias serão movidas')} de volta ao Product Backlog**\n\n"
                "- os critérios de aceitação, pontos, etiqueta MoSCoW e vínculos com épicos serão mantidos\n"
                "- nenhuma história será apagada"
            )
            if not tem_product:
                st.error(str(SemProductBacklog()))
            ciente = st.checkbox(
                "Entendo que as histórias voltam para o product backlog.", key=f"chk_excluir_{backlog.id}"
            )
        else:
            st.write("Este sprint não tem histórias.")
            ciente = True
        if st.button(
            "Excluir sprint",
            type="primary",
            disabled=not ciente or (n > 0 and not tem_product),
            key=f"btn_confirmar_exclusao_{backlog.id}",
        ):
            excluir_e_avisar("Sprint excluído.")
        if st.button("Cancelar", key=f"btn_cancelar_exclusao_{backlog.id}"):
            st.rerun()

    st.dialog(f"Excluir o {backlog.nome}?")(corpo_sprint)()


# ---------- seleção do projeto ----------

def _escolher_projeto(usuario_id: int) -> tuple[int, str] | None:
    lista = projetos.listar(usuario_id)
    if not lista:
        st.info("Crie um projeto na página Projetos para gerenciar seus backlogs.")
        return None
    ids = [p.id for p in lista]
    nomes = {p.id: p.nome for p in lista}
    atual = st.session_state.get(_PROJETO)
    if atual not in ids:
        atual = st.session_state.get("projeto_aberto")
    if atual not in ids:
        atual = ids[0]
    escolhido = st.selectbox(
        "Projeto",
        ids,
        index=ids.index(atual),
        format_func=nomes.get,
        key="seletor_projeto_backlogs",
    )
    if st.session_state.get(_PROJETO) != escolhido:
        st.session_state.pop(_ABERTO, None)  # outro projeto: sai do backlog que estava aberto
    st.session_state[_PROJETO] = escolhido
    return escolhido, nomes[escolhido]


# ---------- lista ----------

def _lista(usuario_id: int, projeto_id: int, projeto_nome: str) -> None:
    conjunto = backlogs.listar(usuario_id, projeto_id)
    product = conjunto.product

    cab, acao = st.columns([4, 2], vertical_alignment="bottom")
    cab.subheader("Product backlog")
    cab.caption("no máximo 1 por projeto")
    if acao.button(
        "+ Novo product backlog",
        key="btn_novo_product",
        disabled=product is not None,
        help=_EXPLICACAO_BLOQUEIO if product else None,
    ):
        _dialogo_product(usuario_id, projeto_id, projeto_nome, None, product)
    if product:
        st.caption(_EXPLICACAO_BLOQUEIO)
        _cartao(usuario_id, product, True, projeto_nome)
    else:
        with st.container(border=True):
            st.write("Este projeto ainda não tem product backlog")
            if st.button("Criar product backlog", type="primary", key="btn_criar_product_vazio"):
                _dialogo_product(usuario_id, projeto_id, projeto_nome, None, None)

    cab, acao = st.columns([4, 2], vertical_alignment="bottom")
    cab.subheader(f"Sprint backlogs {len(conjunto.sprints)}")
    cab.caption("Ciclos de trabalho do projeto, do mais recente ao mais antigo.")
    if acao.button("+ Novo sprint backlog", key="btn_novo_sprint"):
        _dialogo_sprint(usuario_id, projeto_id, projeto_nome, None)
    if not conjunto.sprints:
        st.caption("Este projeto ainda não tem sprint backlogs.")
    for sprint in conjunto.sprints:
        _cartao(usuario_id, sprint, product is not None, projeto_nome)


def _cartao(usuario_id: int, b: BacklogDados, tem_product: bool, projeto_nome: str) -> None:
    with st.container(border=True):
        nome, editar, excluir = st.columns([8, 1, 1], vertical_alignment="center")
        if nome.button(b.nome, key=f"abrir_backlog_{b.id}"):
            st.session_state[_ABERTO] = b.id
            st.rerun()
        if not b.e_product:
            nome.caption(f"{_periodo(b)} · {_ESTADOS.get(b.estado or '', '')}")
        if b.descricao:
            nome.caption(b.descricao)
        nome.caption(_resumo(b))
        if editar.button("✎", key=f"editar_backlog_{b.id}", help="Editar backlog"):
            if b.e_product:
                _dialogo_product(usuario_id, b.projeto_id, projeto_nome, b)
            else:
                _dialogo_sprint(usuario_id, b.projeto_id, projeto_nome, b)
        if excluir.button("🗑", key=f"excluir_backlog_{b.id}", help="Excluir backlog"):
            _dialogo_exclusao(usuario_id, b, tem_product)


# ---------- detalhe ----------

def _detalhe(usuario_id: int, backlog_id: int, projeto_nome: str) -> None:
    try:
        b = backlogs.obter(usuario_id, backlog_id)
    except BacklogNaoEncontrado:
        st.session_state.pop(_ABERTO, None)
        st.rerun()
        return
    conjunto = backlogs.listar(usuario_id, b.projeto_id)
    tem_product = conjunto.product is not None

    if st.button("← Backlogs", key="btn_voltar_backlogs"):
        st.session_state.pop(_ABERTO, None)
        st.rerun()

    topo, editar, excluir = st.columns([6, 2, 2], vertical_alignment="center")
    topo.title(b.nome)
    if editar.button("Editar", key="btn_editar_backlog"):
        if b.e_product:
            _dialogo_product(usuario_id, b.projeto_id, projeto_nome, b)
        else:
            _dialogo_sprint(usuario_id, b.projeto_id, projeto_nome, b)
    if excluir.button("🗑 Excluir", key="btn_excluir_backlog"):
        _dialogo_exclusao(usuario_id, b, tem_product)

    if b.e_product:
        st.caption(f"Product backlog · {projeto_nome}")
    else:
        st.caption(f"Sprint backlog · {_periodo(b)} ({b.duracao_dias} dias) · {_ESTADOS.get(b.estado or '', '')}")
    if b.descricao:
        st.write(b.descricao)

    c1, c2 = st.columns(2)
    c1.metric("Histórias", b.historias)
    c2.metric("Story points", b.pontos)

    backlog_historias.renderizar(usuario_id, b, conjunto)


def pagina_backlogs() -> None:
    usuario = exigir_login()
    _exibir_aviso()
    st.title("Backlogs")
    escolha = _escolher_projeto(usuario.id)
    if escolha is None:
        return
    projeto_id, projeto_nome = escolha
    backlog_id = st.session_state.get(_ABERTO)
    if backlog_id is None:
        _lista(usuario.id, projeto_id, projeto_nome)
    else:
        _detalhe(usuario.id, backlog_id, projeto_nome)
