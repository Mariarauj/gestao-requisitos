"""Tela de acesso: entrar e criar conta. É a única tela disponível sem autenticação."""
import streamlit as st

from sgr.services import autenticacao
from sgr.services.auth_service import (
    ContaBloqueada,
    CredenciaisInvalidas,
    ErroDeValidacao,
)
from sgr.ui.sessao import iniciar_sessao


def _aba_entrar() -> None:
    with st.form("form_entrar"):
        email = st.text_input("E-mail", key="entrar_email")
        senha = st.text_input("Senha", type="password", key="entrar_senha")
        enviar = st.form_submit_button("Entrar", key="btn_entrar", type="primary")
    if not enviar:
        return
    try:
        usuario = autenticacao.autenticar(email, senha)
    except (CredenciaisInvalidas, ContaBloqueada) as erro:
        st.error(str(erro))
        return
    iniciar_sessao(usuario)
    st.rerun()


def _aba_cadastrar() -> None:
    with st.form("form_cadastro"):
        nome = st.text_input("Nome", key="cadastro_nome")
        email = st.text_input("E-mail", key="cadastro_email")
        senha = st.text_input("Senha (mínimo 8 caracteres)", type="password", key="cadastro_senha")
        confirmacao = st.text_input("Confirmar senha", type="password", key="cadastro_confirmacao")
        enviar = st.form_submit_button("Criar conta", key="btn_cadastrar", type="primary")
    if not enviar:
        return
    try:
        autenticacao.cadastrar(nome, email, senha, confirmacao)
    except ErroDeValidacao as erro:
        for mensagem in erro.erros.values():
            st.error(mensagem)
        return
    st.success("Conta criada! Agora entre na aba **Entrar** com seu e-mail e senha.")


def pagina_acesso() -> None:
    st.title("Sistema de Gestão de Requisitos")
    entrar, cadastrar = st.tabs(["Entrar", "Criar conta"])
    with entrar:
        _aba_entrar()
    with cadastrar:
        _aba_cadastrar()
