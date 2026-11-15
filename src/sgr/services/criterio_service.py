"""CRUD de critérios de aceitação (requisitos 12 e 13).

Regras:
- o critério pertence a exatamente uma história e é escrito em campos separados de
  contexto, ação e resultado, todos obrigatórios; o texto padrão
  "Dado [contexto], quando [ação], então [resultado]" é montado a partir deles;
- novos critérios entram no fim da lista; apagar um critério não altera os demais;
- quem tem acesso ao projeto da história gerencia os critérios; fora dele, "não encontrado";
- toda escrita gera registro de auditoria.
"""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Callable

from sqlalchemy.orm import Session

from sgr.db.session import get_session
from sgr.models import CriterioAceitacao
from sgr.repositories import auditoria_repository, criterio_repository, historia_repository
from sgr.services.auth_service import ErroDeValidacao
from sgr.services.texto import MENSAGEM_CARACTERE_INVALIDO, caractere_invalido
from sgr.services.historia_service import CriterioDados, HistoriaNaoEncontrada


class CriterioNaoEncontrado(Exception):
    def __init__(self) -> None:
        super().__init__("Critério de aceitação não encontrado.")


def _validar(contexto: str | None, acao: str | None, resultado: str | None) -> tuple[str, str, str]:
    contexto, acao, resultado = (contexto or "").strip(), (acao or "").strip(), (resultado or "").strip()
    erros = {
        campo: mensagem
        for campo, valor, mensagem in (
            ("contexto", contexto, "Informe o contexto (o estado do sistema antes da ação)."),
            ("acao", acao, "Informe a ação (o que o usuário faz)."),
            ("resultado", resultado, "Informe o resultado esperado."),
        )
        if not valor
    }
    for campo, valor in (("contexto", contexto), ("acao", acao), ("resultado", resultado)):
        if campo not in erros and caractere_invalido(valor):
            erros[campo] = MENSAGEM_CARACTERE_INVALIDO
    if erros:
        raise ErroDeValidacao(erros)
    return contexto, acao, resultado


def _dados(c: CriterioAceitacao) -> CriterioDados:
    return CriterioDados(c.id, c.historia_id, c.contexto, c.acao, c.resultado, c.ordem)


def _snapshot(c: CriterioAceitacao) -> dict:
    return {
        "historia_id": c.historia_id,
        "contexto": c.contexto,
        "acao": c.acao,
        "resultado": c.resultado,
        "ordem": c.ordem,
    }


class CriterioService:
    def __init__(
        self, sessao: Callable[[], AbstractContextManager[Session]] = get_session
    ) -> None:
        self._sessao = sessao

    def listar(self, usuario_id: int, historia_id: int) -> list[CriterioDados]:
        with self._sessao() as sessao:
            historia = self._historia(sessao, usuario_id, historia_id)
            return [_dados(c) for c in criterio_repository.listar(sessao, historia.id)]

    def criar(
        self, usuario_id: int, historia_id: int, contexto: str | None, acao: str | None,
        resultado: str | None,
    ) -> CriterioDados:
        contexto, acao, resultado = _validar(contexto, acao, resultado)
        with self._sessao() as sessao:
            historia = self._historia(sessao, usuario_id, historia_id)
            criterio = criterio_repository.criar(sessao, historia.id, contexto, acao, resultado)
            self._auditar(sessao, usuario_id, criterio, "CRIAR", posterior=_snapshot(criterio))
            return _dados(criterio)

    def atualizar(
        self, usuario_id: int, criterio_id: int, contexto: str | None, acao: str | None,
        resultado: str | None,
    ) -> CriterioDados:
        contexto, acao, resultado = _validar(contexto, acao, resultado)
        with self._sessao() as sessao:
            criterio = self._acessivel(sessao, usuario_id, criterio_id)
            anterior = _snapshot(criterio)
            criterio.contexto, criterio.acao, criterio.resultado = contexto, acao, resultado
            sessao.flush()
            if _snapshot(criterio) != anterior:
                self._auditar(sessao, usuario_id, criterio, "ALTERAR", anterior, _snapshot(criterio))
            return _dados(criterio)

    def excluir(self, usuario_id: int, criterio_id: int) -> None:
        with self._sessao() as sessao:
            criterio = self._acessivel(sessao, usuario_id, criterio_id)
            self._auditar(sessao, usuario_id, criterio, "EXCLUIR", anterior=_snapshot(criterio))
            criterio_repository.excluir(sessao, criterio)

    # ---------- internos ----------

    @staticmethod
    def _auditar(sessao: Session, usuario_id: int, criterio: CriterioAceitacao, operacao: str, anterior=None, posterior=None) -> None:
        auditoria_repository.registrar(
            sessao,
            usuario_id=usuario_id,
            entidade="criterio_aceitacao",
            entidade_id=criterio.id,
            operacao=operacao,
            valor_anterior=anterior,
            valor_posterior=posterior,
        )

    @staticmethod
    def _historia(sessao: Session, usuario_id: int, historia_id: int):
        historia = historia_repository.buscar_acessivel(sessao, usuario_id, historia_id)
        if historia is None:
            raise HistoriaNaoEncontrada()
        return historia

    @staticmethod
    def _acessivel(sessao: Session, usuario_id: int, criterio_id: int) -> CriterioAceitacao:
        criterio = criterio_repository.buscar_acessivel(sessao, usuario_id, criterio_id)
        if criterio is None:
            raise CriterioNaoEncontrado()
        return criterio
