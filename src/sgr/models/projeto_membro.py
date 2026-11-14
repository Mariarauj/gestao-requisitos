from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from sgr.db.base import Base


class ProjetoMembro(Base):
    """Associação N:N entre projeto e usuário."""

    __tablename__ = "projeto_membro"

    projeto_id: Mapped[int] = mapped_column(
        ForeignKey("projeto.id", ondelete="CASCADE"), primary_key=True
    )
    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuario.id", ondelete="CASCADE"), primary_key=True
    )
    entrou_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
