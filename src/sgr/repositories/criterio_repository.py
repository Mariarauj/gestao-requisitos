from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sgr.models import CriterioAceitacao, Historia, Projeto
from sgr.repositories.projeto_repository import filtro_acesso


def buscar_acessivel(session: Session, usuario_id: int, criterio_id: int) -> CriterioAceitacao | None:
    return session.scalar(
        select(CriterioAceitacao)
        .join(Historia, Historia.id == CriterioAceitacao.historia_id)
        .join(Projeto, Projeto.id == Historia.projeto_id)
        .where(CriterioAceitacao.id == criterio_id, filtro_acesso(usuario_id))
    )


def listar(session: Session, historia_id: int) -> list[CriterioAceitacao]:
    return list(
        session.scalars(
            select(CriterioAceitacao)
            .where(CriterioAceitacao.historia_id == historia_id)
            .order_by(CriterioAceitacao.ordem)
        )
    )


def criar(
    session: Session, historia_id: int, contexto: str, acao: str, resultado: str
) -> CriterioAceitacao:
    """Cria o critério no fim da lista (ordem = maior ordem + 1, a partir de 1).

    A linha da história é travada durante o cálculo, para que dois critérios criados ao
    mesmo tempo não recebam a mesma ordem.
    """
    session.execute(select(Historia.id).where(Historia.id == historia_id).with_for_update())
    maior = session.scalar(
        select(func.max(CriterioAceitacao.ordem)).where(CriterioAceitacao.historia_id == historia_id)
    )
    criterio = CriterioAceitacao(
        historia_id=historia_id,
        contexto=contexto,
        acao=acao,
        resultado=resultado,
        ordem=(maior or 0) + 1,
    )
    session.add(criterio)
    session.flush()
    return criterio


def excluir(session: Session, criterio: CriterioAceitacao) -> None:
    session.delete(criterio)
    session.flush()
