from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sgr.db.base import Base
from sgr.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from sgr.models.historia import Historia
    from sgr.models.projeto import Projeto


class Epico(TimestampMixin, Base):
    """Agrupador temático de histórias (relação N:N com história)."""

    __tablename__ = "epico"
    __table_args__ = (
        UniqueConstraint("projeto_id", "nome"),
        Index("ix_epico_projeto", "projeto_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    projeto_id: Mapped[int] = mapped_column(ForeignKey("projeto.id", ondelete="CASCADE"))
    nome: Mapped[str] = mapped_column(String(120))
    descricao: Mapped[str | None] = mapped_column(String(280))

    projeto: Mapped["Projeto"] = relationship(back_populates="epicos")
    # Somente leitura: os vínculos são gravados pela classe EpicoHistoria.
    historias: Mapped[list["Historia"]] = relationship(
        secondary="epico_historia", back_populates="epicos", viewonly=True
    )
