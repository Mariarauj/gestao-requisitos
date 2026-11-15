"""CRUD de épicos (requisito 10).

Regras:
- nome obrigatório (até 120 caracteres), único no projeto sem diferenciar maiúsculas;
  descrição opcional (até 280);
- um épico com histórias não pode ser excluído: primeiro desfaça os vínculos;
- renomear o épico vale para todas as histórias ligadas, pois elas apenas o referenciam;
- quem tem acesso ao projeto gerencia os épicos; fora dele, tudo é "não encontrado";
- toda escrita gera registro de auditoria.
"""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from sgr.db.session import get_session
from sgr.models import Epico
from sgr.repositories import auditoria_repository, epico_repository, projeto_repository, travas
from sgr.services.auth_service import ErroDeValidacao
from sgr.services.texto import MENSAGEM_CARACTERE_INVALIDO, caractere_invalido
from sgr.services.projeto_service import ProjetoNaoEncontrado

NOME_MAX = 120
DESCRICAO_MAX = 280


@dataclass(frozen=True)
class EpicoDados:
    id: int
    projeto_id: int
    nome: str
    descricao: str | None
    historias: int
    pontos: int


@dataclass(frozen=True)
class HistoriaDoEpico:
    id: int
    codigo: str
    papel: str
    acao: str
    beneficio: str
    story_points: int | None
    moscow: str
    backlog_id: int


@dataclass(frozen=True)
class EpicoDetalhe:
    epico: EpicoDados
    historias: tuple[HistoriaDoEpico, ...]


class EpicoNaoEncontrado(Exception):
    def __init__(self) -> None:
        super().__init__("Épico não encontrado.")


class EpicoComHistorias(Exception):
    def __init__(self, quantidade: int) -> None:
        self.quantidade = quantidade
        super().__init__(
            "Não é possível excluir o épico: "
            f"{quantidade} {'história ainda está ligada' if quantidade == 1 else 'histórias ainda estão ligadas'} "
            "a ele. Remova os vínculos primeiro."
        )


class NomeDeEpicoJaUsado(ErroDeValidacao):
    def __init__(self) -> None:
        super().__init__({"nome": "Já existe um épico com este nome neste projeto."})


def _validar(nome: str | None, descricao: str | None) -> tuple[str, str | None]:
    nome = (nome or "").strip()
    descricao = (descricao or "").strip() or None
    erros: dict[str, str] = {}
    if not nome:
        erros["nome"] = "Informe o nome do épico."
    elif caractere_invalido(nome):
        erros["nome"] = MENSAGEM_CARACTERE_INVALIDO
    elif len(nome) > NOME_MAX:
        erros["nome"] = f"O nome deve ter no máximo {NOME_MAX} caracteres."
    if caractere_invalido(descricao):
        erros["descricao"] = MENSAGEM_CARACTERE_INVALIDO
    elif descricao and len(descricao) > DESCRICAO_MAX:
        erros["descricao"] = f"A descrição deve ter no máximo {DESCRICAO_MAX} caracteres."
    if erros:
        raise ErroDeValidacao(erros)
    return nome, descricao


def _snapshot(e: Epico) -> dict:
    return {"nome": e.nome, "descricao": e.descricao}


class EpicoService:
    def __init__(
        self, sessao: Callable[[], AbstractContextManager[Session]] = get_session
    ) -> None:
        self._sessao = sessao

    def listar(self, usuario_id: int, projeto_id: int) -> list[EpicoDados]:
        with self._sessao() as sessao:
            self._projeto(sessao, usuario_id, projeto_id)
            return [
                self._dados(e, qtd, pts) for e, qtd, pts in epico_repository.listar(sessao, projeto_id)
            ]

    def obter(self, usuario_id: int, epico_id: int) -> EpicoDetalhe:
        """Épico com todas as histórias ligadas a ele."""
        with self._sessao() as sessao:
            epico = self._acessivel(sessao, usuario_id, epico_id)
            historias = epico_repository.historias_do_epico(sessao, epico.id)
            return EpicoDetalhe(
                epico=self._dados(epico, len(historias), sum(h.story_points or 0 for h in historias)),
                historias=tuple(
                    HistoriaDoEpico(
                        h.id, h.codigo, h.papel, h.acao, h.beneficio, h.story_points, h.moscow, h.backlog_id
                    )
                    for h in historias
                ),
            )

    def criar(
        self, usuario_id: int, projeto_id: int, nome: str | None, descricao: str | None = None
    ) -> EpicoDados:
        nome, descricao = _validar(nome, descricao)
        with self._sessao() as sessao:
            self._projeto(sessao, usuario_id, projeto_id)
            travas.travar_nomes_de_epico(sessao, projeto_id)  # serializa checar+gravar no projeto
            if epico_repository.existe_nome(sessao, projeto_id, nome):
                raise NomeDeEpicoJaUsado()
            try:
                with sessao.begin_nested():  # o índice único do banco cobre a concorrência
                    epico = epico_repository.criar(sessao, projeto_id, nome, descricao)
            except IntegrityError:
                raise NomeDeEpicoJaUsado() from None
            self._auditar(sessao, usuario_id, epico, "CRIAR", posterior=_snapshot(epico))
            return self._dados(epico, 0, 0)

    def atualizar(
        self, usuario_id: int, epico_id: int, nome: str | None, descricao: str | None = None
    ) -> EpicoDados:
        nome, descricao = _validar(nome, descricao)
        with self._sessao() as sessao:
            epico = self._acessivel(sessao, usuario_id, epico_id)
            travas.travar_nomes_de_epico(sessao, epico.projeto_id)
            if epico_repository.existe_nome(sessao, epico.projeto_id, nome, excluir_id=epico.id):
                raise NomeDeEpicoJaUsado()
            anterior = _snapshot(epico)
            if (nome, descricao) != (epico.nome, epico.descricao):
                try:
                    with sessao.begin_nested():
                        epico.nome, epico.descricao = nome, descricao
                        sessao.flush()
                except IntegrityError:
                    raise NomeDeEpicoJaUsado() from None
                self._auditar(sessao, usuario_id, epico, "ALTERAR", anterior, _snapshot(epico))
            historias = epico_repository.historias_do_epico(sessao, epico.id)
            return self._dados(epico, len(historias), sum(h.story_points or 0 for h in historias))

    def excluir(self, usuario_id: int, epico_id: int) -> None:
        with self._sessao() as sessao:
            epico = self._acessivel(sessao, usuario_id, epico_id)
            ligadas = epico_repository.contar_historias(sessao, epico.id)
            if ligadas:
                raise EpicoComHistorias(ligadas)
            self._auditar(sessao, usuario_id, epico, "EXCLUIR", anterior=_snapshot(epico))
            epico_repository.excluir(sessao, epico)

    # ---------- internos ----------

    @staticmethod
    def _dados(epico: Epico, historias: int, pontos: int) -> EpicoDados:
        return EpicoDados(epico.id, epico.projeto_id, epico.nome, epico.descricao, historias, pontos)

    @staticmethod
    def _auditar(sessao: Session, usuario_id: int, epico: Epico, operacao: str, anterior=None, posterior=None) -> None:
        auditoria_repository.registrar(
            sessao,
            usuario_id=usuario_id,
            entidade="epico",
            entidade_id=epico.id,
            operacao=operacao,
            valor_anterior=anterior,
            valor_posterior=posterior,
        )

    @staticmethod
    def _projeto(sessao: Session, usuario_id: int, projeto_id: int):
        projeto = projeto_repository.buscar_acessivel(sessao, usuario_id, projeto_id)
        if projeto is None:
            raise ProjetoNaoEncontrado()
        return projeto

    @staticmethod
    def _acessivel(sessao: Session, usuario_id: int, epico_id: int) -> Epico:
        epico = epico_repository.buscar_acessivel(sessao, usuario_id, epico_id)
        if epico is None:
            raise EpicoNaoEncontrado()
        return epico
