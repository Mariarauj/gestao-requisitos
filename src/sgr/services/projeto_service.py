"""CRUD de projetos (requisito 4).

Regras:
- nome obrigatório (até 120 caracteres) e único entre os projetos do mesmo proprietário;
- descrição opcional (até 280 caracteres);
- quem cria o projeto é o proprietário e também o primeiro membro;
- proprietário e membros veem o projeto; só o proprietário edita ou exclui;
- projeto de outra pessoa é tratado como inexistente, para não revelar que ele existe;
- toda escrita gera um registro de auditoria.
"""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from sgr.db.session import get_session
from sgr.models import Projeto
from sgr.repositories import auditoria_repository, projeto_repository
from sgr.repositories.projeto_repository import Contagens
from sgr.services.auth_service import ErroDeValidacao

NOME_MAX = 120
DESCRICAO_MAX = 280


@dataclass(frozen=True)
class ProjetoDados:
    """Projeto como a interface o enxerga (sem objetos ligados à sessão do banco)."""

    id: int
    nome: str
    descricao: str | None
    proprietario_id: int
    arquivado: bool
    contagens: Contagens

    def e_proprietario(self, usuario_id: int) -> bool:
        return self.proprietario_id == usuario_id


class ProjetoNaoEncontrado(Exception):
    def __init__(self) -> None:
        super().__init__("Projeto não encontrado.")


class SemPermissao(Exception):
    def __init__(self) -> None:
        super().__init__("Somente o proprietário pode alterar ou excluir o projeto.")


class NomeJaUsado(ErroDeValidacao):
    def __init__(self) -> None:
        super().__init__({"nome": "Você já tem um projeto com este nome."})


def _snapshot(projeto: Projeto) -> dict:
    return {"nome": projeto.nome, "descricao": projeto.descricao}


def _validar(nome: str | None, descricao: str | None) -> tuple[str, str | None]:
    nome = (nome or "").strip()
    descricao = (descricao or "").strip() or None
    erros: dict[str, str] = {}
    if not nome:
        erros["nome"] = "Informe o nome do projeto."
    elif len(nome) > NOME_MAX:
        erros["nome"] = f"O nome deve ter no máximo {NOME_MAX} caracteres."
    if descricao and len(descricao) > DESCRICAO_MAX:
        erros["descricao"] = f"A descrição deve ter no máximo {DESCRICAO_MAX} caracteres."
    if erros:
        raise ErroDeValidacao(erros)
    return nome, descricao


class ProjetoService:
    def __init__(
        self, sessao: Callable[[], AbstractContextManager[Session]] = get_session
    ) -> None:
        self._sessao = sessao

    # ---------- leitura ----------

    def listar(
        self,
        usuario_id: int,
        *,
        busca: str = "",
        apenas_meus: bool = False,
        arquivados: bool = False,
    ) -> list[ProjetoDados]:
        with self._sessao() as sessao:
            projetos = projeto_repository.listar(
                sessao, usuario_id, busca=busca, apenas_meus=apenas_meus, arquivados=arquivados
            )
            contagens = projeto_repository.contagens(sessao, [p.id for p in projetos])
            return [self._dados(p, contagens[p.id]) for p in projetos]

    def obter(self, usuario_id: int, projeto_id: int) -> ProjetoDados:
        with self._sessao() as sessao:
            projeto = self._acessivel(sessao, usuario_id, projeto_id)
            contagens = projeto_repository.contagens(sessao, [projeto.id])[projeto.id]
            return self._dados(projeto, contagens)

    # ---------- escrita ----------

    def criar(self, usuario_id: int, nome: str, descricao: str | None = None) -> ProjetoDados:
        nome, descricao = _validar(nome, descricao)
        with self._sessao() as sessao:
            if projeto_repository.existe_nome(sessao, usuario_id, nome):
                raise NomeJaUsado()
            try:
                # Savepoint: se duas requisições criarem o mesmo nome ao mesmo tempo,
                # a restrição única do banco recusa e tratamos como nome já usado.
                with sessao.begin_nested():
                    projeto = projeto_repository.criar(sessao, nome, descricao, usuario_id)
            except IntegrityError:
                raise NomeJaUsado() from None
            auditoria_repository.registrar(
                sessao,
                usuario_id=usuario_id,
                entidade="projeto",
                entidade_id=projeto.id,
                operacao="CRIAR",
                valor_posterior=_snapshot(projeto),
            )
            return self._dados(projeto, Contagens())

    def atualizar(
        self, usuario_id: int, projeto_id: int, nome: str, descricao: str | None = None
    ) -> ProjetoDados:
        nome, descricao = _validar(nome, descricao)
        with self._sessao() as sessao:
            projeto = self._propria(sessao, usuario_id, projeto_id)
            anterior = _snapshot(projeto)
            if (nome, descricao) != (anterior["nome"], anterior["descricao"]):
                if projeto_repository.existe_nome(
                    sessao, usuario_id, nome, ignorar_id=projeto.id
                ):
                    raise NomeJaUsado()
                try:
                    with sessao.begin_nested():
                        projeto.nome, projeto.descricao = nome, descricao
                        sessao.flush()
                except IntegrityError:
                    raise NomeJaUsado() from None
                auditoria_repository.registrar(
                    sessao,
                    usuario_id=usuario_id,
                    entidade="projeto",
                    entidade_id=projeto.id,
                    operacao="ALTERAR",
                    valor_anterior=anterior,
                    valor_posterior=_snapshot(projeto),
                )
            contagens = projeto_repository.contagens(sessao, [projeto.id])[projeto.id]
            return self._dados(projeto, contagens)

    def excluir(self, usuario_id: int, projeto_id: int) -> Contagens:
        """Exclui o projeto com tudo o que ele contém e devolve o que foi removido."""
        with self._sessao() as sessao:
            projeto = self._propria(sessao, usuario_id, projeto_id)
            removido = projeto_repository.contagens(sessao, [projeto.id])[projeto.id]
            anterior = {
                **_snapshot(projeto),
                "backlogs": removido.backlogs,
                "historias": removido.historias,
                "epicos": removido.epicos,
                "criterios": removido.criterios,
            }
            projeto_repository.excluir(sessao, projeto)
            auditoria_repository.registrar(
                sessao,
                usuario_id=usuario_id,
                entidade="projeto",
                entidade_id=projeto_id,
                operacao="EXCLUIR",
                valor_anterior=anterior,
            )
            return removido

    # ---------- internos ----------

    @staticmethod
    def _dados(projeto: Projeto, contagens: Contagens) -> ProjetoDados:
        return ProjetoDados(
            id=projeto.id,
            nome=projeto.nome,
            descricao=projeto.descricao,
            proprietario_id=projeto.proprietario_id,
            arquivado=projeto.arquivado,
            contagens=contagens,
        )

    @staticmethod
    def _acessivel(sessao: Session, usuario_id: int, projeto_id: int) -> Projeto:
        projeto = projeto_repository.buscar_acessivel(sessao, usuario_id, projeto_id)
        if projeto is None:
            raise ProjetoNaoEncontrado()
        return projeto

    def _propria(self, sessao: Session, usuario_id: int, projeto_id: int) -> Projeto:
        projeto = self._acessivel(sessao, usuario_id, projeto_id)
        if projeto.proprietario_id != usuario_id:
            raise SemPermissao()
        return projeto
