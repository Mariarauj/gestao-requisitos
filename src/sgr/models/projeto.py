from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sgr.db.base import Base
from sgr.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from sgr.models.backlog import Backlog
    from sgr.models.epico import Epico
    from sgr.models.historia import Historia


class Projeto(TimestampMixin, Base):
    """Contêiner de todo o trabalho de um produto; fronteira de isolamento dos dados."""

    __tablename__ = "projeto"
    __table_args__ = (UniqueConstraint("proprietario_id", "nome"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))
    descricao: Mapped[str | None] = mapped_column(String(280))
    proprietario_id: Mapped[int] = mapped_column(
        ForeignKey("usuario.id", ondelete="RESTRICT")
    )
    arquivado: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))

    backlogs: Mapped[list["Backlog"]] = relationship(
        back_populates="projeto", cascade="all, delete-orphan", passive_deletes=True
    )
    historias: Mapped[list["Historia"]] = relationship(
        back_populates="projeto", cascade="all, delete-orphan", passive_deletes=True
    )
    epicos: Mapped[list["Epico"]] = relationship(
        back_populates="projeto", cascade="all, delete-orphan", passive_deletes=True
    )
