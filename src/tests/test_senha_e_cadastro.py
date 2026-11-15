"""Regra de senha, medidor de força e aceite da política no cadastro (Storyboard 1, Q-02/Q-03)."""
from contextlib import contextmanager

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from sgr.services.auth_service import AuthService, EmailJaCadastrado, ErroDeValidacao
from sgr.services.senha import MENSAGEM_REGRA, avaliar_senha

OK = "senha-segura-123"


@pytest.fixture()
def auth(conn):
    @contextmanager
    def sessao():
        s = Session(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    return AuthService(sessao, rounds=4)


def _erros(auth, **campos):
    base = {"nome": "Maria", "email": "maria@empresa.com.br", "senha": OK, "confirmacao": OK}
    with pytest.raises(ErroDeValidacao) as e:
        auth.cadastrar(**{**base, **campos})
    return e.value.erros


# ---------- medidor de força ----------

@pytest.mark.parametrize(
    "senha, nivel, atende",
    [
        ("", "vazia", False),
        ("abc", "fraca", False),
        ("abcdefgh", "fraca", False),  # sem número
        ("12345678", "fraca", False),  # sem letra
        ("abc1", "fraca", False),  # curta
        ("abcdefg1", "boa", True),  # exatamente 8
        ("senha1234", "boa", True),
        ("abcdefghij12", "boa", True),  # 12 caracteres, mas só minúsculas e sem símbolo
        ("Abcdefghij12", "forte", True),  # 12 + maiúscula e minúscula
        ("abcdefghi-12", "forte", True),  # 12 + símbolo
        ("açúcar1234", "boa", True),  # letras acentuadas contam como letra
    ],
)
def test_avaliar_senha(senha, nivel, atende):
    a = avaliar_senha(senha)
    assert (a.nivel, a.atende) == (nivel, atende)


def test_criterios_mostram_o_que_falta():
    a = avaliar_senha("abcdefgh")
    assert [(c.texto, c.atendido) for c in a.criterios] == [
        ("mínimo 8 caracteres", True), ("uma letra", True), ("um número", False),
    ]
    assert [c.atendido for c in avaliar_senha(None).criterios] == [False, False, False]


# ---------- regras e mensagens do cadastro ----------

@pytest.mark.parametrize("senha", ["curta1", "somente-letras", "12345678", "        "])
def test_senha_fora_da_regra_e_recusada_com_a_mensagem_do_storyboard(auth, senha):
    assert _erros(auth, senha=senha, confirmacao=senha)["senha"] == MENSAGEM_REGRA
    assert MENSAGEM_REGRA == "A senha precisa ter pelo menos 8 caracteres, uma letra e um número."


def test_nome_vazio_mostra_a_mensagem_do_storyboard(auth):
    assert _erros(auth, nome="  ")["nome"] == "Informe seu nome."


def test_senhas_diferentes_mostram_a_mensagem_do_storyboard(auth):
    assert _erros(auth, confirmacao=OK + "x") == {"confirmacao": "As senhas não conferem."}


def test_email_ja_cadastrado_mostra_a_mensagem_do_storyboard(auth):
    auth.cadastrar("Maria", "maria@empresa.com.br", OK, OK)
    with pytest.raises(EmailJaCadastrado) as e:
        auth.cadastrar("Outra", "MARIA@empresa.com.br", OK, OK)
    assert e.value.erros == {"email": "Este e-mail já tem conta."}


def test_varios_erros_vem_juntos_para_a_tela_marcar_cada_campo(auth):
    erros = _erros(auth, nome="", email="x", senha="abc", confirmacao="abd")
    assert set(erros) == {"nome", "email", "senha"}  # sem "confirmacao": a senha já está errada


def test_erro_de_senha_nao_cria_conta(auth, conn):
    _erros(auth, senha="abc")
    assert conn.execute(text("SELECT count(*) FROM usuario")).scalar_one() == 0


# ---------- aceite da política de privacidade ----------

def test_recusar_a_politica_impede_o_cadastro(auth, conn):
    assert _erros(auth, politica_aceita=False) == {
        "politica": "Aceite a política de privacidade para criar a conta."
    }
    assert conn.execute(text("SELECT count(*) FROM usuario")).scalar_one() == 0


def _auditoria_do_cadastro(conn):
    return conn.execute(
        text("SELECT valor_posterior FROM registro_auditoria WHERE entidade='usuario' AND operacao='CRIAR'")
    ).scalar_one()


def test_aceite_fica_registrado_na_auditoria(auth, conn):
    auth.cadastrar("Maria", "maria@empresa.com.br", OK, OK, politica_aceita=True)
    assert _auditoria_do_cadastro(conn) == {
        "nome": "Maria", "email": "maria@empresa.com.br", "politica_privacidade_aceita": True,
    }


def test_sem_informar_o_aceite_o_cadastro_segue_e_nao_registra_aceite(auth, conn):
    auth.cadastrar("Maria", "maria@empresa.com.br", OK, OK)
    assert "politica_privacidade_aceita" not in _auditoria_do_cadastro(conn)


def test_senha_nao_aparece_na_auditoria(auth, conn):
    auth.cadastrar("Maria", "maria@empresa.com.br", OK, OK, politica_aceita=True)
    assert OK not in str(_auditoria_do_cadastro(conn))
