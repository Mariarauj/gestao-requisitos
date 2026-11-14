from sqlalchemy import BigInteger, cast, func, select, text
from sqlalchemy.orm import Session

from sgr.models import Backlog, CriterioAceitacao, Epico, EpicoHistoria, Historia, Projeto
from sgr.repositories.projeto_repository import filtro_acesso

PREFIXO_CODIGO = "SGR-"


def buscar_acessivel(session: Session, usuario_id: int, historia_id: int) -> Historia | None:
    """História de um projeto que o usuário possui ou do qual é membro."""
    return session.scalar(
        select(Historia)
        .join(Projeto, Projeto.id == Historia.projeto_id)
        .where(Historia.id == historia_id, filtro_acesso(usuario_id))
    )


def proximo_codigo(session: Session, projeto_id: int) -> str:
    """Próximo código legível do projeto (SGR-1, SGR-2...).

    Usa o maior número já existente + 1, sob trava por projeto, para que duas criações
    simultâneas não escolham o mesmo código. A numeração reinicia em cada projeto.
    """
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:chave))"), {"chave": f"historia:{projeto_id}"}
    )
    maior = session.scalar(
        select(func.max(cast(func.substring(Historia.codigo, "[0-9]+$"), BigInteger))).where(
            Historia.projeto_id == projeto_id
        )
    )
    return f"{PREFIXO_CODIGO}{(maior or 0) + 1}"


def criar(
    session: Session,
    *,
    projeto_id: int,
    backlog_id: int,
    codigo: str,
    papel: str,
    acao: str,
    beneficio: str,
    story_points: int | None,
    moscow: str,
) -> Historia:
    historia = Historia(
        projeto_id=projeto_id,
        backlog_id=backlog_id,
        codigo=codigo,
        papel=papel,
        acao=acao,
        beneficio=beneficio,
        story_points=story_points,
        moscow=moscow,
    )
    session.add(historia)
    session.flush()
    return historia


def listar(
    session: Session,
    projeto_id: int,
    backlog_id: int | None = None,
    epico_id: int | None = None,
    moscow: str | None = None,
) -> list[Historia]:
    consulta = select(Historia).where(Historia.projeto_id == projeto_id).order_by(Historia.id)
    if backlog_id is not None:
        consulta = consulta.where(Historia.backlog_id == backlog_id)
    if moscow is not None:
        consulta = consulta.where(Historia.moscow == moscow)
    if epico_id is not None:
        consulta = consulta.where(
            Historia.id.in_(select(EpicoHistoria.historia_id).where(EpicoHistoria.epico_id == epico_id))
        )
    return list(session.scalars(consulta))


def epicos_por_historia(session: Session, historia_ids: list[int]) -> dict[int, list[tuple[int, str]]]:
    resultado: dict[int, list[tuple[int, str]]] = {i: [] for i in historia_ids}
    if historia_ids:
        linhas = session.execute(
            select(EpicoHistoria.historia_id, Epico.id, Epico.nome)
            .join(Epico, Epico.id == EpicoHistoria.epico_id)
            .where(EpicoHistoria.historia_id.in_(historia_ids))
            .order_by(Epico.nome)
        )
        for historia_id, epico_id, nome in linhas:
            resultado[historia_id].append((epico_id, nome))
    return resultado


def contar_criterios(session: Session, historia_ids: list[int]) -> dict[int, int]:
    resultado = {i: 0 for i in historia_ids}
    if historia_ids:
        linhas = session.execute(
            select(CriterioAceitacao.historia_id, func.count(CriterioAceitacao.id))
            .where(CriterioAceitacao.historia_id.in_(historia_ids))
            .group_by(CriterioAceitacao.historia_id)
        )
        resultado.update({h: int(n) for h, n in linhas})
    return resultado


def backlogs_por_id(session: Session, backlog_ids: set[int]) -> dict[int, tuple[str, str]]:
    if not backlog_ids:
        return {}
    linhas = session.execute(
        select(Backlog.id, Backlog.nome, Backlog.tipo).where(Backlog.id.in_(backlog_ids))
    )
    return {i: (nome, tipo) for i, nome, tipo in linhas}


def excluir(session: Session, historia: Historia) -> None:
    """Remove a história; critérios e vínculos com épicos saem por CASCADE."""
    session.delete(historia)
    session.flush()
