from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from sgr.db.base import Base


class RegistroAuditoria(Base):
    """Log de operações de escrita. Referencia as demais tabelas por (entidade, entidade_id),
    sem chave estrangeira física."""

    __tablename__ = "registro_auditoria"
    __table_args__ = (
        CheckConstraint(
            "entidade IN ('projeto', 'backlog', 'historia', 'criterio_aceitacao', 'epico', 'usuario')",
            name="entidade",
        ),
        CheckConstraint("operacao IN ('CRIAR', 'ALTERAR', 'EXCLUIR')", name="operacao"),
        Index("ix_auditoria_entidade", "entidade", "entidade_id", "ocorrido_em"),
        Index("ix_auditoria_usuario", "usuario_id", "ocorrido_em"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id", ondelete="SET NULL"))
    entidade: Mapped[str] = mapped_column(String(30))
    entidade_id: Mapped[int]
    operacao: Mapped[str] = mapped_column(String(8))
    valor_anterior: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    valor_posterior: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    ocorrido_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
