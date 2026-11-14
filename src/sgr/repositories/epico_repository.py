from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from sgr.models import Epico, EpicoHistoria, Historia, Projeto
from sgr.repositories.projeto_repository import filtro_acesso


def buscar_acessivel(session: Session, usuario_id: int, epico_id: int) -> Epico | None:
    return session.scalar(
        select(Epico)
        .join(Projeto, Projeto.id == Epico.projeto_id)
        .where(Epico.id == epico_id, filtro_acesso(usuario_id))
    )


def existe_nome(session: Session, projeto_id: int, nome: str, excluir_id: int | None = None) -> bool:
    """Nome já usado por outro épico do mesmo projeto (sem diferenciar maiúsculas)."""
    consulta = select(Epico.id).where(
        Epico.projeto_id == projeto_id, func.lower(Epico.nome) == func.lower(nome)
    )
    if excluir_id is not None:
        consulta = consulta.where(Epico.id != excluir_id)
    return session.scalar(consulta.limit(1)) is not None


def criar(session: Session, projeto_id: int, nome: str, descricao: str | None) -> Epico:
    epico = Epico(projeto_id=projeto_id, nome=nome, descricao=descricao)
    session.add(epico)
    session.flush()
    return epico


def listar(session: Session, projeto_id: int) -> list[tuple[Epico, int, int]]:
    """Épicos do projeto com a quantidade de histórias e a soma dos story points."""
    linhas = session.execute(
        select(Epico, func.count(EpicoHistoria.historia_id), func.coalesce(func.sum(Historia.story_points), 0))
        .outerjoin(EpicoHistoria, EpicoHistoria.epico_id == Epico.id)
        .outerjoin(Historia, Historia.id == EpicoHistoria.historia_id)
        .where(Epico.projeto_id == projeto_id)
        .group_by(Epico.id)
        .order_by(func.lower(Epico.nome), Epico.id)
    )
    return [(e, int(qtd), int(pts)) for e, qtd, pts in linhas]


def historias_do_epico(session: Session, epico_id: int) -> list[Historia]:
    return list(
        session.scalars(
            select(Historia)
            .join(EpicoHistoria, EpicoHistoria.historia_id == Historia.id)
            .where(EpicoHistoria.epico_id == epico_id)
            .order_by(Historia.id)
        )
    )


def contar_historias(session: Session, epico_id: int) -> int:
    return session.scalar(
        select(func.count()).select_from(EpicoHistoria).where(EpicoHistoria.epico_id == epico_id)
    ) or 0


def validos_do_projeto(session: Session, projeto_id: int, epico_ids: set[int]) -> set[int]:
    """Dos ids informados, os que existem e pertencem ao projeto."""
    if not epico_ids:
        return set()
    return set(
        session.scalars(select(Epico.id).where(Epico.projeto_id == projeto_id, Epico.id.in_(epico_ids)))
    )


def ids_vinculados(session: Session, historia_id: int) -> set[int]:
    return set(
        session.scalars(select(EpicoHistoria.epico_id).where(EpicoHistoria.historia_id == historia_id))
    )


def vincular(session: Session, historia_id: int, epico_ids: set[int]) -> None:
    for epico_id in sorted(epico_ids):
        session.add(EpicoHistoria(epico_id=epico_id, historia_id=historia_id))
    session.flush()


def desvincular(session: Session, historia_id: int, epico_ids: set[int]) -> None:
    if epico_ids:
        session.execute(
            delete(EpicoHistoria).where(
                EpicoHistoria.historia_id == historia_id, EpicoHistoria.epico_id.in_(epico_ids)
            )
        )


def excluir(session: Session, epico: Epico) -> None:
    session.delete(epico)
    session.flush()
