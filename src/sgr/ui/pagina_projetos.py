"""Projetos (requisito 4): lista, criar, ver, editar e excluir — Storyboard 1.

Tudo acontece numa única página: a lista é a visão inicial e, ao abrir um projeto, a mesma
página mostra o painel dele (`projeto_aberto` em st.session_state). Criar, editar e excluir
usam diálogos modais; o retorno de sucesso é um toast mostrado na tela seguinte.
"""
import streamlit as st

from sgr.services import projetos
from sgr.services.auth_service import ErroDeValidacao
from sgr.services.projeto_service import (
    DESCRICAO_MAX,
    NOME_MAX,
    ProjetoDados,
    ProjetoNaoEncontrado,
    SemPermissao,
)
from sgr.repositories.projeto_repository import Contagens
from sgr.ui.sessao import exigir_login

_ABERTO = "projeto_aberto"
_AVISO = "aviso_projeto"
_FILTROS = ["Todos", "Meus projetos", "Arquivados"]


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n <= 1 else plural}"


def _resumo(c: Contagens) -> str:
    partes = [_plural(c.backlogs, "backlog", "backlogs"), _plural(c.historias, "história", "histórias")]
    if c.pontos:
        partes.append(_plural(c.pontos, "ponto", "pontos"))
    return " · ".join(partes)


def _avisar(mensagem: str) -> None:
    """Guarda o aviso para o toast da próxima execução (um st.rerun() logo depois o perderia)."""
    st.session_state[_AVISO] = mensagem


def _exibir_aviso() -> None:
    mensagem = st.session_state.pop(_AVISO, None)
    if mensagem:
        st.toast(mensagem, icon="✅")


# ---------- diálogos ----------

def _dialogo_formulario(usuario_id: int, projeto: ProjetoDados | None) -> None:
    """Criar (projeto=None) ou editar: o mesmo formulário, mudando só título e botão."""
    editando = projeto is not None
    sufixo = projeto.id if editando else "novo"

    def corpo() -> None:
        with st.form(f"form_projeto_{sufixo}", border=False):
            nome = st.text_input(
                "Nome do projeto *",
                value=projeto.nome if editando else "",
                max_chars=NOME_MAX,
                placeholder="Ex.: Portal do Cliente",
                key=f"projeto_nome_{sufixo}",
            )
            erro_nome = st.empty()
            descricao = st.text_area(
                "Descrição",
                value=(projeto.descricao or "") if editando else "",
                max_chars=DESCRICAO_MAX,
                placeholder="Para que serve este projeto?",
                key=f"projeto_descricao_{sufixo}",
            )
            erro_descricao = st.empty()
            if editando:
                st.caption("Alterar nome e descrição não afeta backlogs, histórias nem critérios de aceitação.")
            enviar = st.form_submit_button(
                "Salvar alterações" if editando else "Criar projeto",
                type="primary",
                key=f"btn_salvar_projeto_{sufixo}",
            )
        if st.button("Cancelar", key=f"btn_cancelar_projeto_{sufixo}"):
            st.rerun()
        if not enviar:
            return
        try:
            if editando:
                projetos.atualizar(usuario_id, projeto.id, nome, descricao)
                _avisar("Alterações salvas.")
            else:
                projetos.criar(usuario_id, nome, descricao)
                _avisar("Projeto criado.")
        except ErroDeValidacao as erro:  # os dados digitados continuam nos campos
            if "nome" in erro.erros:
                erro_nome.error(erro.erros["nome"])
            if "descricao" in erro.erros:
                erro_descricao.error(erro.erros["descricao"])
            return
        except (ProjetoNaoEncontrado, SemPermissao) as erro:
            st.error(str(erro))
            return
        st.rerun()

    st.dialog("Editar projeto" if editando else "Novo projeto")(corpo)()


def _dialogo_exclusao(usuario_id: int, projeto: ProjetoDados) -> None:
    def corpo() -> None:
        c = projeto.contagens
        st.write("Esta ação removerá permanentemente:")
        st.markdown(
            "\n".join(
                [
                    f"- {_plural(c.product_backlogs, 'product backlog', 'product backlogs')}",
                    f"- {_plural(c.sprint_backlogs, 'sprint backlog', 'sprint backlogs')}",
                    f"- {_plural(c.historias, 'história de usuário', 'histórias de usuário')}",
                    f"- {_plural(c.epicos, 'épico', 'épicos')} e "
                    f"{_plural(c.criterios, 'critério de aceitação', 'critérios de aceitação')}",
                ]
            )
        )
        ciente = st.checkbox(
            "Entendo que esta ação não pode ser desfeita.", key=f"chk_excluir_{projeto.id}"
        )
        if st.button(
            "Excluir definitivamente",
            type="primary",
            disabled=not ciente,
            key=f"btn_confirmar_exclusao_{projeto.id}",
        ):
            try:
                projetos.excluir(usuario_id, projeto.id)
            except (ProjetoNaoEncontrado, SemPermissao) as erro:
                st.error(str(erro))
                return
            st.session_state.pop(_ABERTO, None)
            _avisar("Projeto excluído.")
            st.rerun()
        if st.button("Cancelar", key=f"btn_cancelar_exclusao_{projeto.id}"):
            st.rerun()

    st.dialog(f"Excluir projeto '{projeto.nome}'?")(corpo)()


# ---------- lista ----------

def _lista(usuario_id: int) -> None:
    topo, acao = st.columns([4, 1], vertical_alignment="center")
    topo.title("Projetos")
    if acao.button("+ Novo projeto", type="primary", key="btn_novo_projeto"):
        _dialogo_formulario(usuario_id, None)

    filtro = st.radio("Filtro", _FILTROS, horizontal=True, label_visibility="collapsed", key="filtro_projetos")
    busca = st.text_input("Buscar projeto", placeholder="Buscar projeto...", key="busca_projetos")

    lista = projetos.listar(
        usuario_id,
        busca=busca,
        apenas_meus=filtro == "Meus projetos",
        arquivados=filtro == "Arquivados",
    )

    if not lista:
        if filtro == "Todos" and not busca.strip():
            with st.container(border=True):
                st.subheader("Você ainda não tem projetos")
                if st.button("Criar meu primeiro projeto", type="primary", key="btn_primeiro_projeto"):
                    _dialogo_formulario(usuario_id, None)
        else:
            st.info("Nenhum projeto encontrado.")
        return

    for p in lista:
        with st.container(border=True):
            nome, editar, excluir = st.columns([8, 1, 1], vertical_alignment="center")
            if nome.button(p.nome, key=f"abrir_{p.id}"):
                st.session_state[_ABERTO] = p.id
                st.rerun()
            nome.caption(_resumo(p.contagens))
            if p.e_proprietario(usuario_id):
                if editar.button("✎", key=f"editar_{p.id}", help="Editar projeto"):
                    _dialogo_formulario(usuario_id, p)
                if excluir.button("🗑", key=f"excluir_{p.id}", help="Excluir projeto"):
                    _dialogo_exclusao(usuario_id, p)


# ---------- detalhe ----------

def _detalhe(usuario_id: int, projeto_id: int) -> None:
    try:
        p = projetos.obter(usuario_id, projeto_id)
    except ProjetoNaoEncontrado:
        st.session_state.pop(_ABERTO, None)
        st.rerun()
        return

    if st.button("← Projetos", key="btn_voltar_projetos"):
        st.session_state.pop(_ABERTO, None)
        st.rerun()

    topo, editar, excluir = st.columns([6, 2, 2], vertical_alignment="center")
    topo.title(p.nome)
    if p.e_proprietario(usuario_id):
        if editar.button("Editar projeto", key="btn_editar_projeto"):
            _dialogo_formulario(usuario_id, p)
        if excluir.button("🗑 Excluir", key="btn_excluir_projeto"):
            _dialogo_exclusao(usuario_id, p)
    if p.descricao:
        st.write(p.descricao)

    c = p.contagens
    colunas = st.columns(5)
    for coluna, (rotulo, valor) in zip(
        colunas,
        [
            ("Product backlog", c.product_backlogs),
            ("Sprint backlogs", c.sprint_backlogs),
            ("Épicos", c.epicos),
            ("Histórias", c.historias),
            ("Story points", c.pontos),
        ],
    ):
        coluna.metric(rotulo, valor)


def pagina_projetos() -> None:
    usuario = exigir_login()
    _exibir_aviso()
    projeto_id = st.session_state.get(_ABERTO)
    if projeto_id is None:
        _lista(usuario.id)
    else:
        _detalhe(usuario.id, projeto_id)
