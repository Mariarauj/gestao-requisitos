"""Política de privacidade exibida no cadastro (Storyboard 1, Q-02).

TEXTO PROVISÓRIO do protótipo: descreve apenas o que o sistema realmente coleta e faz hoje.
A política oficial da equipe deve substituí-lo, sem prazos ou direitos que o sistema não cumpra.
"""
import streamlit as st

TEXTO = """
**Dados coletados**
- Nome e e-mail, informados no cadastro.
- Senha, guardada somente como *hash* (bcrypt); o sistema nunca guarda a senha em texto.
- Registros de auditoria: quem criou, alterou ou excluiu cada item e quando.

**Finalidade**
Identificar você, controlar o acesso ao sistema e registrar quem fez cada alteração.

**Aceite**
Ao criar a conta você declara ter lido esta política. O aceite fica registrado.
"""


@st.dialog("Política de privacidade")
def ler_politica() -> None:
    st.markdown(TEXTO)
    st.caption("Texto provisório do protótipo, a ser substituído pela política oficial.")
    if st.button("Fechar", key="btn_fechar_politica"):
        st.rerun()
