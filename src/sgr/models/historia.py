from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CHAR,
    CheckConstraint,
    ForeignKey,
    Integer,
    Index,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sgr.db.base import Base
from sgr.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from sgr.models.backlog import Backlog
    from sgr.models.criterio_aceitacao import CriterioAceitacao
    from sgr.models.epico import Epico
    from sgr.models.projeto import Projeto


class Historia(TimestampMixin, Base):
    """História de usuário: "Como um [papel] eu quero [ação] para [benefício]".

    A pontuação RICE não é armazenada: é calculada pela camada de serviço a partir
    das quatro entradas rice_*.
    """

    __tablename__ = "historia"
    __table_args__ = (
        UniqueConstraint("projeto_id", "codigo"),
        CheckConstraint(
            "story_points IN (0, 1, 2, 3, 5, 8, 13, 21, 34, 55)", name="story_points"
        ),
        CheckConstraint("moscow IN ('M', 'S', 'C', 'W')", name="moscow"),
        CheckConstraint("rice_reach >= 0", name="rice_reach"),
        CheckConstraint("rice_impact IN (3, 2, 1, 0.5, 0.25)", name="rice_impact"),
        CheckConstraint("rice_confidence IN (100, 80, 50)", name="rice_confidence"),
        # O esforço aceita a escala dos story points, exceto o zero (divisão da fórmula RICE).
        CheckConstraint(
            "rice_effort IN (1, 2, 3, 5, 8, 13, 21, 34, 55)", name="rice_effort"
        ),
        CheckConstraint(
            "(rice_reach IS NULL AND rice_impact IS NULL AND rice_confidence IS NULL "
            "AND rice_effort IS NULL) OR (rice_reach IS NOT NULL AND rice_impact IS NOT NULL "
            "AND rice_confidence IS NOT NULL AND rice_effort IS NOT NULL)",
            name="rice_completo",
        ),
        Index("ix_historia_backlog", "backlog_id"),
        Index("ix_historia_projeto", "projeto_id"),
        Index(
            "ix_historia_backlog_rice",
            "backlog_id",
            "rice_reach",
            "rice_impact",
            "rice_confidence",
            "rice_effort",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    projeto_id: Mapped[int] = mapped_column(ForeignKey("projeto.id", ondelete="CASCADE"))
    backlog_id: Mapped[int] = mapped_column(ForeignKey("backlog.id", ondelete="RESTRICT"))
    codigo: Mapped[str] = mapped_column(String(12))
    papel: Mapped[str] = mapped_column(String(120))
    acao: Mapped[str] = mapped_column(String(200))
    beneficio: Mapped[str] = mapped_column(String(200))
    story_points: Mapped[int | None] = mapped_column(SmallInteger)
    moscow: Mapped[str] = mapped_column(CHAR(1))
    rice_reach: Mapped[int | None] = mapped_column(Integer)
    rice_impact: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    rice_confidence: Mapped[int | None] = mapped_column(SmallInteger)
    rice_effort: Mapped[int | None] = mapped_column(SmallInteger)

    projeto: Mapped["Projeto"] = relationship(back_populates="historias")
    backlog: Mapped["Backlog"] = relationship(back_populates="historias")
    criterios: Mapped[list["CriterioAceitacao"]] = relationship(
        back_populates="historia",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="CriterioAceitacao.ordem",
    )
    # Somente leitura: os vínculos são gravados pela classe EpicoHistoria.
    epicos: Mapped[list["Epico"]] = relationship(
        secondary="epico_historia", back_populates="historias", viewonly=True
    )
