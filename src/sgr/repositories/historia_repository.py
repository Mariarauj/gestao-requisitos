from sqlalchemy import BigInteger, Numeric, cast, func, select, text, update
from sqlalchemy.orm import Session

from sgr.models import Backlog, CriterioAceitacao, Epico, EpicoHistoria, Historia, Projeto
from sgr.repositories.projeto_repository import filtro_acesso

PREFIXO_CODIGO = "SGR-"


def rice_sql():
    """Nota RICE calculada no banco, para filtrar e ordenar sem trazer tudo para a memória.

    É a mesma conta de services.rice.calcular_rice, com o mesmo arredondamento (duas casas,
    metade para cima; as entradas nunca são negativas). Quem altera uma altera a outra:
    tests/test_rice_listagem.py compara as duas em todo o domínio. Sem RICE (colunas nulas),
    o resultado é NULL; o CHECK ck_historia_rice_completo garante "as quatro ou nenhuma", e
    rice_effort nunca é zero.
    """
    bruto = (cast(Historia.rice_reach, Numeric) * Historia.rice_impact * Historia.rice_confidence) / (
        100 * Historia.rice_effort
    )
    return func.round(cast(bruto, Numeric), 2)


def buscar_acessivel(session: Session, usuario_id: int, historia_id: int) -> Historia | None:
    """História de um projeto que o usuário possui ou do qual é membro."""
    return session.scalar(
        select(Historia)
        .join(Projeto, Projeto.id == Historia.projeto_id)
        .where(Historia.id == historia_id, filtro_acesso(usuario_id))
    )


def buscar_acessiveis_travadas(
    session: Session, usuario_id: int, historia_ids: set[int]
) -> list[Historia]:
    """Histórias acessíveis ao usuário, em ordem de id, com a linha travada (FOR UPDATE).

    Travar na ordem do id evita impasse entre duas movimentações que cruzam as mesmas
    histórias; a segunda espera a primeira terminar e já lê o backlog atualizado.
    """
    return list(
        session.scalars(
            select(Historia)
            .join(Projeto, Projeto.id == Historia.projeto_id)
            .where(Historia.id.in_(historia_ids), filtro_acesso(usuario_id))
            .order_by(Historia.id)
            .with_for_update(of=Historia)
        )
    )


def mover_para_backlog(session: Session, historia_ids: list[int], backlog_id: int) -> None:
    """Troca só o backlog das histórias: código, critérios, pontos, etiqueta, RICE e épicos
    não dependem do backlog e ficam intactos."""
    session.execute(update(Historia).where(Historia.id.in_(historia_ids)).values(backlog_id=backlog_id))


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
    *,
    rice_min=None,
    rice_max=None,
    com_rice: bool | None = None,
    ordenar_por: str = "posicao",
    ordem: str | None = None,
) -> list[Historia]:
    """Histórias do projeto. Padrão: da mais antiga para a mais nova.

    `rice_min`/`rice_max` são inclusivos e comparam com a nota arredondada que o usuário vê;
    história sem RICE nunca passa por eles. `ordenar_por="rice"` ordena da maior nota para a
    menor (ou `ordem="asc"`), com as sem RICE sempre no fim e a ordem de criação como desempate.
    """
    consulta = select(Historia).where(Historia.projeto_id == projeto_id)
    if backlog_id is not None:
        consulta = consulta.where(Historia.backlog_id == backlog_id)
    if moscow is not None:
        consulta = consulta.where(Historia.moscow == moscow)
    if epico_id is not None:
        consulta = consulta.where(
            Historia.id.in_(select(EpicoHistoria.historia_id).where(EpicoHistoria.epico_id == epico_id))
        )
    if com_rice is True:
        consulta = consulta.where(Historia.rice_reach.is_not(None))
    elif com_rice is False:
        consulta = consulta.where(Historia.rice_reach.is_(None))
    nota = rice_sql()
    if rice_min is not None:
        consulta = consulta.where(nota >= rice_min)
    if rice_max is not None:
        consulta = consulta.where(nota <= rice_max)
    if ordenar_por == "rice":
        chave = nota.asc() if ordem == "asc" else nota.desc()
        consulta = consulta.order_by(chave.nulls_last(), Historia.id)
    else:
        consulta = consulta.order_by(Historia.id.desc() if ordem == "desc" else Historia.id)
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
