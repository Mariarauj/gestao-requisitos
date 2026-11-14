"""Consultas e gravações de backlog (product e sprint). Sem regra de negócio."""
from datetime import date

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from sgr.models import Backlog, Historia, Projeto
from sgr.repositories.projeto_repository import filtro_acesso


def buscar_acessivel(session: Session, usuario_id: int, backlog_id: int) -> Backlog | None:
    """Backlog de um projeto que o usuário possui ou do qual é membro."""
    return session.scalar(
        select(Backlog)
        .join(Projeto, Projeto.id == Backlog.projeto_id)
        .where(Backlog.id == backlog_id, filtro_acesso(usuario_id))
    )


def por_ids(session: Session, backlog_ids: set[int]) -> dict[int, Backlog]:
    if not backlog_ids:
        return {}
    return {b.id: b for b in session.scalars(select(Backlog).where(Backlog.id.in_(backlog_ids)))}


def product_do_projeto(session: Session, projeto_id: int) -> Backlog | None:
    return session.scalar(
        select(Backlog).where(Backlog.projeto_id == projeto_id, Backlog.tipo == "PRODUCT")
    )


def sprints_do_projeto(session: Session, projeto_id: int) -> list[Backlog]:
    """Do mais recente ao mais antigo."""
    return list(
        session.scalars(
            select(Backlog)
            .where(Backlog.projeto_id == projeto_id, Backlog.tipo == "SPRINT")
            .order_by(Backlog.data_inicio.desc(), Backlog.id.desc())
        )
    )


def contar_sprints(session: Session, projeto_id: int) -> int:
    return session.scalar(
        select(func.count()).where(Backlog.projeto_id == projeto_id, Backlog.tipo == "SPRINT")
    ) or 0


def contagens(session: Session, backlog_ids: list[int]) -> dict[int, tuple[int, int]]:
    """(histórias, pontos) de cada backlog, numa consulta só."""
    if not backlog_ids:
        return {}
    linhas = session.execute(
        select(Historia.backlog_id, func.count(), func.coalesce(func.sum(Historia.story_points), 0))
        .where(Historia.backlog_id.in_(backlog_ids))
        .group_by(Historia.backlog_id)
    )
    encontrados = {bid: (qtd, int(pts)) for bid, qtd, pts in linhas}
    return {bid: encontrados.get(bid, (0, 0)) for bid in backlog_ids}


def listar_historias(session: Session, backlog_id: int) -> list[Historia]:
    return list(
        session.scalars(select(Historia).where(Historia.backlog_id == backlog_id).order_by(Historia.id))
    )


def criar_product(session: Session, projeto_id: int, nome: str, descricao: str | None) -> Backlog:
    backlog = Backlog(projeto_id=projeto_id, tipo="PRODUCT", nome=nome, descricao=descricao)
    session.add(backlog)
    session.flush()  # dispara o índice único de um product backlog por projeto
    return backlog


def criar_sprint(
    session: Session, projeto_id: int, nome: str, descricao: str | None, inicio: date, fim: date
) -> Backlog:
    backlog = Backlog(
        projeto_id=projeto_id,
        tipo="SPRINT",
        nome=nome,
        descricao=descricao,
        data_inicio=inicio,
        data_fim=fim,
        estado="PLANEJADO",
    )
    session.add(backlog)
    session.flush()
    return backlog


def devolver_historias(session: Session, de_backlog_id: int, para_backlog_id: int) -> list[int]:
    """Move todas as histórias de um backlog para outro e devolve os ids movidos."""
    ids = list(session.scalars(select(Historia.id).where(Historia.backlog_id == de_backlog_id)))
    if ids:
        session.execute(
            update(Historia).where(Historia.id.in_(ids)).values(backlog_id=para_backlog_id)
        )
    return ids


def excluir(session: Session, backlog: Backlog) -> None:
    session.delete(backlog)
    session.flush()
