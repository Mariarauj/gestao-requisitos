"""Telas de acesso, as únicas disponíveis sem sessão (Storyboard 1, Q-01 a Q-04 e Q-06).

- Q-01 entrar;  Q-02/Q-03 criar conta, com erro no campo e sem apagar o que foi digitado;
- Q-04 confirmação de conta criada (a sessão já começa autenticada);
- Q-06 sessão expirada e acesso a endereço interno sem sessão.

Não existem "Continuar conectado" e "Esqueci minha senha" (Q-01, Q-07 B): o primeiro exige
sessão persistente entre recargas e o segundo exige envio de e-mail e tokens de uso único, que
o sistema ainda não tem. Ver o resumo da issue #30.
"""
import streamlit as st

from sgr.services import autenticacao
from sgr.services.auth_service import (
    ContaBloqueada,
    CredenciaisInvalidas,
    EmailJaCadastrado,
    ErroDeValidacao,
)
from sgr.services.senha import avaliar_senha
from sgr.ui import sessao as ses
from sgr.ui.politica import ler_politica

_MODO = "acesso_modo"  # "entrar" ou "criar"
_CONTA_CRIADA = "conta_criada"
CAMPOS_CADASTRO = (
    "cadastro_nome", "cadastro_email", "cadastro_senha", "cadastro_confirmacao", "cadastro_politica",
)


def _cabecalho() -> None:
    st.title("SGR")
    st.caption("Sistema de Gestão de Requisitos")


def _centralizar():
    _, meio, _ = st.columns([1, 3, 1])
    return meio


# ---------- callbacks (rodam antes do próximo desenho da tela) ----------

def _ir_para_entrar(email: str | None = None) -> None:
    st.session_state[_MODO] = "entrar"
    ses.definir_motivo(ses.ENTRAR)
    if email:
        st.session_state["entrar_email"] = email


def _ir_para_criar() -> None:
    st.session_state[_MODO] = "criar"
    ses.definir_motivo(ses.ENTRAR)


def _entrar_como_outro_usuario() -> None:
    ses.esquecer_ultimo_email()
    st.session_state.pop("entrar_email", None)
    _ir_para_entrar()


# ---------- Q-01 entrar ----------

def _tela_entrar() -> None:
    if ses.ultimo_email() and "entrar_email" not in st.session_state:
        st.session_state["entrar_email"] = ses.ultimo_email()  # volta da sessão expirada
    with _centralizar():
        _cabecalho()
        with st.container(border=True):
            st.subheader("Entrar")
            with st.form("form_entrar", border=False):
                email = st.text_input("E-mail ★", key="entrar_email", placeholder="seu@email.com")
                st.caption("Use o e-mail cadastrado na sua conta.")
                senha = st.text_input("Senha ★", type="password", key="entrar_senha")
                enviar = st.form_submit_button("Entrar", key="btn_entrar", type="primary")
            erro = st.empty()
            st.caption("Ainda não tem conta?")
            st.button("Criar conta", key="btn_ir_cadastro", on_click=_ir_para_criar)
        st.caption("Dados tratados conforme a LGPD — finalidade informada no cadastro.")
    if not enviar:
        return
    try:
        usuario = autenticacao.autenticar(email, senha)
    except (CredenciaisInvalidas, ContaBloqueada) as falha:
        erro.error(str(falha))
        return
    ses.iniciar_sessao(usuario)
    st.rerun()


# ---------- Q-02 / Q-03 criar conta ----------

def _medidor_de_forca(senha: str) -> None:
    """Força da senha e os critérios, atualizados enquanto a pessoa digita (Q-02)."""
    regra = "mínimo 8 caracteres · uma letra e um número"
    if not senha:
        st.caption(regra)
        return
    avaliacao = avaliar_senha(senha)
    st.caption(f"Força da senha: {avaliacao.nivel}")
    st.progress({"fraca": 1, "boa": 2, "forte": 3}[avaliacao.nivel] / 3)
    st.caption(" · ".join(f"{'✓' if c.atendido else '⚠'} {c.texto}" for c in avaliacao.criterios))


def _tela_criar_conta() -> None:
    with _centralizar():
        _cabecalho()
        with st.container(border=True):
            st.subheader("Criar conta")
            nome = st.text_input("Nome ★", key="cadastro_nome", placeholder="Como você quer ser chamado")
            erro_nome = st.empty()
            email = st.text_input("E-mail ★", key="cadastro_email", placeholder="seu@email.com")
            erro_email = st.empty()
            senha = st.text_input("Senha ★", type="password", key="cadastro_senha")
            _medidor_de_forca(senha)
            erro_senha = st.empty()
            confirmacao = st.text_input("Confirmar senha ★", type="password", key="cadastro_confirmacao")
            erro_confirmacao = st.empty()
            aceite = st.checkbox("Li e aceito a política de privacidade.", key="cadastro_politica")
            if st.button("Ler a política de privacidade", key="btn_ler_politica"):
                ler_politica()
            erro_politica = st.empty()
            enviar = st.button("Criar conta", key="btn_cadastrar", type="primary")
            st.caption("Já tem conta?")
            st.button("Entrar", key="btn_ir_entrar", on_click=_ir_para_entrar)
    if not enviar:
        return
    try:
        usuario = autenticacao.cadastrar(nome, email, senha, confirmacao, politica_aceita=aceite)
    except ErroDeValidacao as erro:  # nada é apagado: a pessoa só corrige o campo apontado
        destinos = {
            "nome": erro_nome, "email": erro_email, "senha": erro_senha,
            "confirmacao": erro_confirmacao, "politica": erro_politica,
        }
        for campo, mensagem in erro.erros.items():
            destinos[campo].error(mensagem)
        if isinstance(erro, EmailJaCadastrado):  # Q-03 B: oferece a saída em vez de só recusar
            with erro_email.container():
                st.error(erro.erros["email"])
                st.button(
                    "Entrar com este e-mail", key="btn_entrar_com_email",
                    on_click=_ir_para_entrar, args=(email.strip(),),
                )
        return
    ses.iniciar_sessao(usuario)  # o cadastro já autentica (Q-04)
    st.session_state[_CONTA_CRIADA] = True
    st.rerun()


# ---------- Q-04 conta criada ----------

def _comecar_agora() -> None:
    nome = ses.usuario_logado().nome.split()[0]
    st.session_state.pop(_CONTA_CRIADA, None)
    st.session_state["ir_para_projetos"] = True
    st.session_state["aviso_boas_vindas"] = f"Bem-vindo, {nome}."


def conta_recem_criada() -> bool:
    return bool(st.session_state.get(_CONTA_CRIADA))


def tela_conta_criada() -> None:
    for campo in CAMPOS_CADASTRO + (_MODO,):  # senhas digitadas não ficam no estado da sessão
        st.session_state.pop(campo, None)
    with _centralizar():
        _cabecalho()
        with st.container(border=True):
            st.subheader("✓ Conta criada.")
            st.write("Você já pode usar o sistema.")
            st.info("No primeiro acesso, seus projetos e backlogs aparecem vazios. Comece criando um projeto.")
            st.button("Começar agora", key="btn_comecar_agora", type="primary", on_click=_comecar_agora)


# ---------- Q-06 guarda de acesso ----------

def _tela_sessao_expirada() -> None:
    with _centralizar():
        _cabecalho()
        with st.container(border=True):
            st.subheader("◷ Sua sessão expirou")
            st.write(
                f"Por segurança, encerramos sua sessão após {ses.horas_de_sessao()} horas de "
                "inatividade. Entre novamente para continuar."
            )
            st.button("Entrar novamente", key="btn_entrar_novamente", type="primary", on_click=_ir_para_entrar)
            st.button("Continuar como outro usuário", key="btn_outro_usuario", on_click=_entrar_como_outro_usuario)


def _tela_acesso_negado() -> None:
    with _centralizar():
        _cabecalho()
        with st.container(border=True):
            st.subheader("🔒 Você precisa entrar para acessar esta página")
            st.write("O endereço que você tentou abrir exige autenticação.")
            st.button("Entrar", key="btn_entrar_acesso", type="primary", on_click=_ir_para_entrar)
            st.caption("Após entrar, você será levado de volta ao que estava tentando abrir.")


def pagina_acesso() -> None:
    """Escolhe a tela de acesso certa para o motivo pelo qual a pessoa está sem sessão."""
    motivo = ses.motivo_de_acesso()
    if motivo == ses.EXPIRADA:
        return _tela_sessao_expirada()
    if motivo == ses.SEM_SESSAO:
        return _tela_acesso_negado()
    if motivo == ses.SAIU:
        st.toast("Você saiu do sistema.", icon="✅")  # uma vez só: o motivo volta ao normal
        ses.definir_motivo(ses.ENTRAR)
    if st.session_state.get(_MODO) == "criar":
        _tela_criar_conta()
    else:
        _tela_entrar()
