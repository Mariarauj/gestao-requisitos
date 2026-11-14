from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from sgr.db.base import Base


class EpicoHistoria(Base):
    """Vínculo N:N entre épico e história.

    Épico com histórias não pode ser excluído (RESTRICT); excluir a história desfaz o vínculo (CASCADE).
    """

    __tablename__ = "epico_historia"
    __table_args__ = (Index("ix_epico_historia_historia", "historia_id"),)

    epico_id: Mapped[int] = mapped_column(
        ForeignKey("epico.id", ondelete="RESTRICT"), primary_key=True
    )
    historia_id: Mapped[int] = mapped_column(
        ForeignKey("historia.id", ondelete="CASCADE"), primary_key=True
    )
    vinculado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
