"""Consultas e gravações de projeto. Sem regra de negócio (permissões ficam no serviço)."""
from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from sgr.models import Backlog, CriterioAceitacao, Epico, Historia, Projeto, ProjetoMembro


@dataclass(frozen=True)
class Contagens:
    """Inventário de um projeto: o que existe dentro dele."""

    product_backlogs: int = 0
    sprint_backlogs: int = 0
    historias: int = 0
    pontos: int = 0
    epicos: int = 0
    criterios: int = 0

    @property
    def backlogs(self) -> int:
        return self.product_backlogs + self.sprint_backlogs


def _filtro_acesso(usuario_id: int):
    """O usuário vê projetos que possui ou dos quais é membro."""
    membro = select(ProjetoMembro.projeto_id).where(ProjetoMembro.usuario_id == usuario_id)
    return or_(Projeto.proprietario_id == usuario_id, Projeto.id.in_(membro))


def listar(
    session: Session,
    usuario_id: int,
    *,
    busca: str = "",
    apenas_meus: bool = False,
    arquivados: bool = False,
) -> list[Projeto]:
    consulta = select(Projeto).where(Projeto.arquivado.is_(arquivados))
    consulta = consulta.where(
        Projeto.proprietario_id == usuario_id if apenas_meus else _filtro_acesso(usuario_id)
    )
    termo = busca.strip()
    if termo:
        escapado = termo.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        consulta = consulta.where(Projeto.nome.ilike(f"%{escapado}%", escape="\\"))
    return list(session.scalars(consulta.order_by(func.lower(Projeto.nome), Projeto.id)))


def buscar_acessivel(session: Session, usuario_id: int, projeto_id: int) -> Projeto | None:
    return session.scalar(
        select(Projeto).where(Projeto.id == projeto_id, _filtro_acesso(usuario_id))
    )


def existe_nome(
    session: Session, proprietario_id: int, nome: str, ignorar_id: int | None = None
) -> bool:
    """Nome já usado pelo mesmo proprietário (sem diferenciar maiúsculas)."""
    consulta = select(Projeto.id).where(
        Projeto.proprietario_id == proprietario_id, func.lower(Projeto.nome) == nome.lower()
    )
    if ignorar_id is not None:
        consulta = consulta.where(Projeto.id != ignorar_id)
    return session.scalar(consulta.limit(1)) is not None


def criar(session: Session, nome: str, descricao: str | None, proprietario_id: int) -> Projeto:
    projeto = Projeto(nome=nome, descricao=descricao, proprietario_id=proprietario_id)
    session.add(projeto)
    session.flush()  # materializa o id e dispara as restrições do banco
    session.add(ProjetoMembro(projeto_id=projeto.id, usuario_id=proprietario_id))
    session.flush()
    return projeto


def contagens(session: Session, projeto_ids: list[int]) -> dict[int, Contagens]:
    """Inventário de vários projetos de uma vez (evita uma consulta por linha da lista)."""
    if not projeto_ids:
        return {}
    resultado = {pid: Contagens() for pid in projeto_ids}

    backlogs = select(Backlog.projeto_id, Backlog.tipo, func.count()).where(
        Backlog.projeto_id.in_(projeto_ids)
    ).group_by(Backlog.projeto_id, Backlog.tipo)
    parcial: dict[int, dict[str, int]] = {pid: {} for pid in projeto_ids}
    for pid, tipo, qtd in session.execute(backlogs):
        parcial[pid][tipo] = qtd

    historias = select(
        Historia.projeto_id, func.count(), func.coalesce(func.sum(Historia.story_points), 0)
    ).where(Historia.projeto_id.in_(projeto_ids)).group_by(Historia.projeto_id)
    hist = {pid: (qtd, int(pts)) for pid, qtd, pts in session.execute(historias)}

    epicos = select(Epico.projeto_id, func.count()).where(
        Epico.projeto_id.in_(projeto_ids)
    ).group_by(Epico.projeto_id)
    epic = dict(session.execute(epicos).tuples().all())

    criterios = (
        select(Historia.projeto_id, func.count(CriterioAceitacao.id))
        .join(CriterioAceitacao, CriterioAceitacao.historia_id == Historia.id)
        .where(Historia.projeto_id.in_(projeto_ids))
        .group_by(Historia.projeto_id)
    )
    crit = dict(session.execute(criterios).tuples().all())

    for pid in projeto_ids:
        qtd_h, pts = hist.get(pid, (0, 0))
        resultado[pid] = Contagens(
            product_backlogs=parcial[pid].get("PRODUCT", 0),
            sprint_backlogs=parcial[pid].get("SPRINT", 0),
            historias=qtd_h,
            pontos=pts,
            epicos=epic.get(pid, 0),
            criterios=crit.get(pid, 0),
        )
    return resultado


def excluir(session: Session, projeto: Projeto) -> None:
    """Remove o projeto e, em cascata, tudo o que pertence a ele."""
    session.delete(projeto)
    session.flush()
