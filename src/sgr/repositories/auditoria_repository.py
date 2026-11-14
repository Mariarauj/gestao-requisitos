from typing import Any

from sqlalchemy.orm import Session

from sgr.models import RegistroAuditoria


def registrar(
    session: Session,
    *,
    usuario_id: int | None,
    entidade: str,
    entidade_id: int,
    operacao: str,
    valor_anterior: dict[str, Any] | None = None,
    valor_posterior: dict[str, Any] | None = None,
) -> RegistroAuditoria:
    registro = RegistroAuditoria(
        usuario_id=usuario_id,
        entidade=entidade,
        entidade_id=entidade_id,
        operacao=operacao,
        valor_anterior=valor_anterior,
        valor_posterior=valor_posterior,
    )
    session.add(registro)
    session.flush()
    return registro
