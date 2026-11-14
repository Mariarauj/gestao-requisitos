"""Priorização da história: story points, etiqueta MoSCoW e critérios RICE (requisitos 14 a 19).

Regras:
- story points só aceitam a escala 0, 1, 2, 3, 5, 8, 13, 21, 34, 55; None remove a estimativa;
- MoSCoW é obrigatório e só aceita M, S, C ou W (a história nunca fica sem etiqueta);
- RICE tem quatro entradas obrigatórias e juntas (Reach, Impact, Confidence, Effort), com
  domínios fechados; não existe RICE parcial. A nota (R × I × C) / E é calculada por
  services/rice.py e nunca é digitada nem gravada;
- as três dimensões são independentes: alterar uma não toca as outras;
- quem tem acesso ao projeto prioriza as histórias; fora dele, tudo é "não encontrado";
- toda alteração real gera registro de auditoria (repetir o mesmo valor não gera).

A validação aqui é a segunda barreira; a terceira são as CHECK constraints do banco.
"""
from __future__ import annotations

from contextlib import AbstractContextManager
from decimal import Decimal
from typing import Callable

from sqlalchemy.orm import Session

from sgr.db.session import get_session
from sgr.models import Historia
from sgr.repositories import auditoria_repository, historia_repository
from sgr.services.auth_service import ErroDeValidacao
from sgr.services.historia_service import (
    MOSCOW,
    STORY_POINTS,
    HistoriaDados,
    HistoriaNaoEncontrada,
    HistoriaService,
)
from sgr.services.rice import calcular_rice, validar_rice

_CAMPOS_RICE = ("rice_reach", "rice_impact", "rice_confidence", "rice_effort")


def validar_story_points(story_points) -> int | None:
    if story_points is None:
        return None
    if isinstance(story_points, bool) or story_points not in STORY_POINTS:
        valores = ", ".join(str(v) for v in STORY_POINTS)
        raise ErroDeValidacao({"story_points": f"Story points inválido. Valores aceitos: {valores}."})
    return int(story_points)


def validar_moscow(moscow: str | None) -> str:
    valor = (moscow or "").strip().upper()
    if not valor:
        raise ErroDeValidacao({"moscow": "Informe a etiqueta MoSCoW (M, S, C ou W)."})
    if valor not in MOSCOW:
        raise ErroDeValidacao({"moscow": "Etiqueta MoSCoW inválida. Valores aceitos: M, S, C, W."})
    return valor


def _numero(valor):
    """Valores para o registro de auditoria (JSON não guarda Decimal)."""
    return float(valor) if isinstance(valor, Decimal) else valor


class PriorizacaoService:
    def __init__(
        self, sessao: Callable[[], AbstractContextManager[Session]] = get_session
    ) -> None:
        self._sessao = sessao

    # ---------- story points ----------

    def definir_story_points(
        self, usuario_id: int, historia_id: int, story_points: int | None
    ) -> HistoriaDados:
        """Atribui os story points da história; None remove a estimativa."""
        story_points = validar_story_points(story_points)
        return self._alterar(usuario_id, historia_id, {"story_points": story_points})

    # ---------- MoSCoW ----------

    def definir_moscow(self, usuario_id: int, historia_id: int, moscow: str | None) -> HistoriaDados:
        """Atribui a etiqueta MoSCoW (M, S, C ou W; aceita minúscula e espaços)."""
        return self._alterar(usuario_id, historia_id, {"moscow": validar_moscow(moscow)})

    # ---------- RICE ----------

    def definir_rice(
        self,
        usuario_id: int,
        historia_id: int,
        reach: int | None,
        impact,
        confidence: int | None,
        effort: int | None,
    ) -> HistoriaDados:
        """Grava as quatro entradas do RICE de uma vez. A nota sai em HistoriaDados.rice."""
        r, i, c, e = validar_rice(reach, impact, confidence, effort)
        return self._alterar(
            usuario_id,
            historia_id,
            {"rice_reach": r, "rice_impact": i, "rice_confidence": c, "rice_effort": e},
        )

    def limpar_rice(self, usuario_id: int, historia_id: int) -> HistoriaDados:
        """Remove o RICE inteiro (as quatro entradas juntas, nunca só algumas)."""
        return self._alterar(usuario_id, historia_id, dict.fromkeys(_CAMPOS_RICE))

    @staticmethod
    def calcular_rice(reach, impact, confidence, effort) -> Decimal:
        """Pré-visualização da nota para o formulário, sem gravar nada."""
        return calcular_rice(reach, impact, confidence, effort)

    # ---------- interno ----------

    def _alterar(self, usuario_id: int, historia_id: int, novos: dict) -> HistoriaDados:
        with self._sessao() as sessao:
            historia = historia_repository.buscar_acessivel(sessao, usuario_id, historia_id)
            if historia is None:
                raise HistoriaNaoEncontrada()
            anterior = {campo: _numero(getattr(historia, campo)) for campo in novos}
            posterior = {campo: _numero(valor) for campo, valor in novos.items()}
            if posterior != anterior:
                for campo, valor in novos.items():
                    setattr(historia, campo, valor)
                sessao.flush()
                self._auditar(sessao, usuario_id, historia, anterior, posterior)
            return HistoriaService._dados(sessao, [historia])[0]

    @staticmethod
    def _auditar(sessao: Session, usuario_id: int, historia: Historia, anterior: dict, posterior: dict) -> None:
        auditoria_repository.registrar(
            sessao,
            usuario_id=usuario_id,
            entidade="historia",
            entidade_id=historia.id,
            operacao="ALTERAR",
            valor_anterior=anterior,
            valor_posterior=posterior,
        )
