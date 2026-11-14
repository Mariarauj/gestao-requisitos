from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, SmallInteger, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sgr.db.base import Base
from sgr.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from sgr.models.historia import Historia


class CriterioAceitacao(TimestampMixin, Base):
    """Critério de aceitação: "Dado [contexto] quando [ação] então [resultado]"."""

    __tablename__ = "criterio_aceitacao"
    __table_args__ = (
        UniqueConstraint("historia_id", "ordem"),
        Index("ix_criterio_historia", "historia_id", "ordem"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    historia_id: Mapped[int] = mapped_column(ForeignKey("historia.id", ondelete="CASCADE"))
    contexto: Mapped[str] = mapped_column(Text)
    acao: Mapped[str] = mapped_column(Text)
    resultado: Mapped[str] = mapped_column(Text)
    ordem: Mapped[int] = mapped_column(SmallInteger)

    historia: Mapped["Historia"] = relationship(back_populates="criterios")
