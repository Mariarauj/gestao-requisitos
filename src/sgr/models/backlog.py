from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sgr.db.base import Base
from sgr.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from sgr.models.historia import Historia
    from sgr.models.projeto import Projeto


class Backlog(TimestampMixin, Base):
    """Product backlog (tipo PRODUCT, um por projeto) ou sprint backlog (tipo SPRINT)."""

    __tablename__ = "backlog"
    __table_args__ = (
        CheckConstraint("tipo IN ('PRODUCT', 'SPRINT')", name="tipo"),
        CheckConstraint(
            "estado IN ('PLANEJADO', 'EM_ANDAMENTO', 'ENCERRADO')", name="estado"
        ),
        CheckConstraint(
            "(tipo = 'PRODUCT' AND data_inicio IS NULL AND data_fim IS NULL AND estado IS NULL) "
            "OR (tipo = 'SPRINT' AND data_inicio IS NOT NULL AND data_fim IS NOT NULL "
            "AND estado IS NOT NULL)",
            name="tipo_atributos",
        ),
        CheckConstraint("tipo <> 'SPRINT' OR data_fim > data_inicio", name="periodo"),
        # No máximo um product backlog por projeto (sprints são ilimitados).
        Index(
            "ux_backlog_product_por_projeto",
            "projeto_id",
            unique=True,
            postgresql_where=text("tipo = 'PRODUCT'"),
        ),
        Index("ix_backlog_projeto_tipo", "projeto_id", "tipo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    projeto_id: Mapped[int] = mapped_column(ForeignKey("projeto.id", ondelete="CASCADE"))
    tipo: Mapped[str] = mapped_column(String(8))
    nome: Mapped[str] = mapped_column(String(120))
    descricao: Mapped[str | None] = mapped_column(String(280))
    data_inicio: Mapped[date | None] = mapped_column(Date)
    data_fim: Mapped[date | None] = mapped_column(Date)
    estado: Mapped[str | None] = mapped_column(String(12))

    projeto: Mapped["Projeto"] = relationship(back_populates="backlogs")
    historias: Mapped[list["Historia"]] = relationship(
        back_populates="backlog", passive_deletes="all"
    )
