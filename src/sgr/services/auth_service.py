"""Cadastro de contas e autenticação (requisitos 2 e 3).

Senhas são guardadas apenas como hash bcrypt. As mensagens de erro de login são genéricas
para não revelar se um e-mail está cadastrado.
"""
from __future__ import annotations

import re
from contextlib import AbstractContextManager
from dataclasses import dataclass
from functools import cached_property
from typing import Callable

import bcrypt
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from sgr.db.session import get_session
from sgr.repositories import auditoria_repository, usuario_repository
from sgr.services.limitador import LimitadorTentativas
from sgr.services.texto import MENSAGEM_CARACTERE_INVALIDO, caractere_invalido

NOME_MAX = 120
EMAIL_MAX = 160
SENHA_MIN = 8
SENHA_MAX_BYTES = 72  # limite do bcrypt
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(frozen=True)
class UsuarioAutenticado:
    """Dados do usuário que a interface pode guardar na sessão (nunca o hash da senha)."""

    id: int
    nome: str
    email: str


class ErroDeValidacao(Exception):
    """Dados inválidos. `erros` mapeia o campo para a mensagem a exibir."""

    def __init__(self, erros: dict[str, str]) -> None:
        super().__init__("; ".join(erros.values()))
        self.erros = erros


class EmailJaCadastrado(ErroDeValidacao):
    def __init__(self) -> None:
        super().__init__({"email": "Este e-mail já está cadastrado."})


class CredenciaisInvalidas(Exception):
    def __init__(self) -> None:
        super().__init__("E-mail ou senha incorretos.")


class ContaBloqueada(Exception):
    def __init__(self, segundos: int) -> None:
        self.segundos = segundos
        minutos = max(1, -(-segundos // 60))
        super().__init__(f"Muitas tentativas incorretas. Tente novamente em {minutos} min.")


def normalizar_email(email: str | None) -> str:
    return (email or "").strip().lower()


class AuthService:
    def __init__(
        self,
        sessao: Callable[[], AbstractContextManager[Session]] = get_session,
        limitador: LimitadorTentativas | None = None,
        rounds: int = 12,
    ) -> None:
        self._sessao = sessao
        self._limitador = limitador or LimitadorTentativas()
        self._rounds = rounds

    # ---------- senha ----------

    def _gerar_hash(self, senha: str) -> str:
        return bcrypt.hashpw(senha.encode("utf-8"), bcrypt.gensalt(self._rounds)).decode("ascii")

    @cached_property
    def _hash_falso(self) -> str:
        # Usado quando o e-mail não existe, para que o tempo de resposta seja parecido.
        return self._gerar_hash("senha-inexistente")

    @staticmethod
    def _conferir(senha: str, hash_: str) -> bool:
        dados = senha.encode("utf-8")
        if len(dados) > SENHA_MAX_BYTES:
            return False
        try:
            return bcrypt.checkpw(dados, hash_.encode("ascii"))
        except ValueError:
            return False

    # ---------- cadastro ----------

    def cadastrar(self, nome: str, email: str, senha: str, confirmacao: str) -> UsuarioAutenticado:
        nome = (nome or "").strip()
        email = normalizar_email(email)
        senha = senha or ""

        erros: dict[str, str] = {}
        if not nome:
            erros["nome"] = "Informe o nome."
        elif caractere_invalido(nome):
            erros["nome"] = MENSAGEM_CARACTERE_INVALIDO
        elif len(nome) > NOME_MAX:
            erros["nome"] = f"O nome deve ter no máximo {NOME_MAX} caracteres."
        if not email:
            erros["email"] = "Informe o e-mail."
        elif caractere_invalido(email) or len(email) > EMAIL_MAX or not _EMAIL_RE.match(email):
            erros["email"] = "Informe um e-mail válido."
        if caractere_invalido(senha):
            erros["senha"] = "A senha contém um caractere inválido."
        elif len(senha) < SENHA_MIN:
            erros["senha"] = f"A senha deve ter pelo menos {SENHA_MIN} caracteres."
        elif len(senha.encode("utf-8")) > SENHA_MAX_BYTES:
            erros["senha"] = f"A senha deve ter no máximo {SENHA_MAX_BYTES} bytes."
        if "senha" not in erros and senha != (confirmacao or ""):
            erros["confirmacao"] = "A confirmação não coincide com a senha."
        if erros:
            raise ErroDeValidacao(erros)

        senha_hash = self._gerar_hash(senha)
        with self._sessao() as sessao:
            if usuario_repository.buscar_por_email(sessao, email):
                raise EmailJaCadastrado()
            try:
                # Savepoint: se outra requisição gravar o mesmo e-mail ao mesmo tempo,
                # o índice único do banco recusa e tratamos como e-mail já cadastrado.
                with sessao.begin_nested():
                    usuario = usuario_repository.criar(sessao, nome, email, senha_hash)
            except IntegrityError:
                raise EmailJaCadastrado() from None
            auditoria_repository.registrar(
                sessao,
                usuario_id=usuario.id,
                entidade="usuario",
                entidade_id=usuario.id,
                operacao="CRIAR",
                valor_posterior={"nome": usuario.nome, "email": usuario.email},
            )
            return UsuarioAutenticado(usuario.id, usuario.nome, usuario.email)

    # ---------- login ----------

    def autenticar(self, email: str, senha: str) -> UsuarioAutenticado:
        chave = normalizar_email(email)
        senha = senha or ""
        # Texto que o banco não guarda nunca é credencial válida: segue o mesmo caminho de uma
        # senha errada (inclusive o hash falso), sem consultar o banco com esse valor.
        entrada_invalida = caractere_invalido(chave) or caractere_invalido(senha)
        restante = self._limitador.segundos_restantes(chave)
        if restante:
            raise ContaBloqueada(restante)

        with self._sessao() as sessao:
            usuario = None if entrada_invalida else usuario_repository.buscar_por_email(sessao, chave)
            hash_ = usuario.senha_hash if usuario else self._hash_falso
            senha_ok = False if entrada_invalida else self._conferir(senha, hash_)
            if not (usuario and usuario.ativo and senha_ok):
                self._limitador.registrar_falha(chave)
                raise CredenciaisInvalidas()
            self._limitador.limpar(chave)
            return UsuarioAutenticado(usuario.id, usuario.nome, usuario.email)
