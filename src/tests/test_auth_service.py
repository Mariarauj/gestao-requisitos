"""Regras de cadastro e autenticação (requisitos 2 e 3)."""
from contextlib import contextmanager

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from sgr.services.auth_service import (
    AuthService,
    ContaBloqueada,
    CredenciaisInvalidas,
    EmailJaCadastrado,
    ErroDeValidacao,
)
from sgr.services.limitador import LimitadorTentativas

SENHA = "senha-segura-123"


class RelogioFalso:
    def __init__(self) -> None:
        self.agora = 1000.0

    def __call__(self) -> float:
        return self.agora


@pytest.fixture()
def relogio():
    return RelogioFalso()


@pytest.fixture()
def servico(conn, relogio):
    """AuthService ligado à transação do teste: os commits viram savepoints e tudo é revertido."""

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

    limitador = LimitadorTentativas(max_falhas=5, janela_s=900, relogio=relogio)
    return AuthService(sessao=sessao, limitador=limitador, rounds=4)


def _cadastrar(servico, **kw):
    dados = {"nome": "Ana Souza", "email": "ana@exemplo.com", "senha": SENHA, "confirmacao": SENHA}
    dados.update(kw)
    return servico.cadastrar(**dados)


# ---------- cadastro ----------

def test_cadastro_cria_conta_com_hash_bcrypt(servico, conn):
    usuario = _cadastrar(servico)
    assert usuario.nome == "Ana Souza" and usuario.email == "ana@exemplo.com"
    senha_hash = conn.execute(text("SELECT senha_hash FROM usuario WHERE id = :i"), {"i": usuario.id}).scalar_one()
    assert senha_hash.startswith("$2") and len(senha_hash) == 60
    assert SENHA not in senha_hash


def test_cadastro_normaliza_email_e_recusa_duplicado(servico):
    _cadastrar(servico, email="  Ana@Exemplo.COM ")
    with pytest.raises(EmailJaCadastrado):
        _cadastrar(servico, email="ANA@exemplo.com")


def test_cadastro_registra_auditoria_sem_senha(servico, conn):
    usuario = _cadastrar(servico)
    linha = conn.execute(
        text("SELECT usuario_id, entidade, entidade_id, operacao, valor_anterior, valor_posterior "
             "FROM registro_auditoria")
    ).one()
    assert (linha.usuario_id, linha.entidade, linha.entidade_id, linha.operacao) == (
        usuario.id, "usuario", usuario.id, "CRIAR")
    assert linha.valor_anterior is None
    assert linha.valor_posterior == {"nome": "Ana Souza", "email": "ana@exemplo.com"}


@pytest.mark.parametrize("campos,chave", [
    ({"nome": "   "}, "nome"),
    ({"nome": "x" * 121}, "nome"),
    ({"email": ""}, "email"),
    ({"email": "sem-arroba"}, "email"),
    ({"email": "a@b"}, "email"),
    ({"email": "a" * 160 + "@x.com"}, "email"),
    ({"senha": "curta", "confirmacao": "curta"}, "senha"),
    ({"senha": "a" * 73, "confirmacao": "a" * 73}, "senha"),
    ({"confirmacao": "outra-senha-123"}, "confirmacao"),
])
def test_cadastro_valida_campos(servico, conn, campos, chave):
    with pytest.raises(ErroDeValidacao) as erro:
        _cadastrar(servico, **campos)
    assert chave in erro.value.erros
    assert conn.execute(text("SELECT count(*) FROM usuario")).scalar_one() == 0


def test_cadastro_informa_todos_os_erros_de_uma_vez(servico):
    with pytest.raises(ErroDeValidacao) as erro:
        servico.cadastrar("", "x", "1", "2")
    assert set(erro.value.erros) == {"nome", "email", "senha"}


def test_senha_com_acentos_e_limite_de_bytes(servico):
    _cadastrar(servico, senha="Çenha-ção-123", confirmacao="Çenha-ção-123")
    assert servico.autenticar("ana@exemplo.com", "Çenha-ção-123").nome == "Ana Souza"


# ---------- login ----------

def test_login_com_credenciais_corretas(servico):
    criado = _cadastrar(servico)
    autenticado = servico.autenticar("ANA@exemplo.com ", SENHA)
    assert autenticado == criado


def test_login_senha_errada_e_email_inexistente_tem_mesma_mensagem(servico):
    _cadastrar(servico)
    with pytest.raises(CredenciaisInvalidas) as a:
        servico.autenticar("ana@exemplo.com", "senha-errada-1")
    with pytest.raises(CredenciaisInvalidas) as b:
        servico.autenticar("naoexiste@exemplo.com", SENHA)
    assert str(a.value) == str(b.value)


def test_login_recusa_conta_inativa(servico, conn):
    usuario = _cadastrar(servico)
    conn.execute(text("UPDATE usuario SET ativo = false WHERE id = :i"), {"i": usuario.id})
    with pytest.raises(CredenciaisInvalidas):
        servico.autenticar("ana@exemplo.com", SENHA)


def test_login_com_senha_muito_longa_nao_quebra(servico):
    _cadastrar(servico)
    with pytest.raises(CredenciaisInvalidas):
        servico.autenticar("ana@exemplo.com", "a" * 200)


def test_bloqueia_apos_cinco_falhas_e_libera_depois_da_janela(servico, relogio):
    _cadastrar(servico)
    for _ in range(5):
        with pytest.raises(CredenciaisInvalidas):
            servico.autenticar("ana@exemplo.com", "errada-123456")
    with pytest.raises(ContaBloqueada) as bloqueio:
        servico.autenticar("ana@exemplo.com", SENHA)  # mesmo a senha certa é recusada
    assert 0 < bloqueio.value.segundos <= 900
    relogio.agora += 901
    assert servico.autenticar("ana@exemplo.com", SENHA).email == "ana@exemplo.com"


def test_login_correto_zera_o_contador_de_falhas(servico):
    _cadastrar(servico)
    for _ in range(4):
        with pytest.raises(CredenciaisInvalidas):
            servico.autenticar("ana@exemplo.com", "errada-123456")
    servico.autenticar("ana@exemplo.com", SENHA)
    for _ in range(4):
        with pytest.raises(CredenciaisInvalidas):
            servico.autenticar("ana@exemplo.com", "errada-123456")
    servico.autenticar("ana@exemplo.com", SENHA)  # ainda não bloqueou


def test_bloqueio_vale_tambem_para_email_inexistente(servico):
    for _ in range(5):
        with pytest.raises(CredenciaisInvalidas):
            servico.autenticar("fantasma@exemplo.com", "qualquer-123")
    with pytest.raises(ContaBloqueada):
        servico.autenticar("fantasma@exemplo.com", "qualquer-123")
