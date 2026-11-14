from sqlalchemy import Boolean, String, text
from sqlalchemy.orm import Mapped, mapped_column

from sgr.db.base import Base
from sgr.models.mixins import TimestampMixin


class Usuario(TimestampMixin, Base):
    """Identidade autenticada do sistema."""

    __tablename__ = "usuario"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(160), unique=True)
    senha_hash: Mapped[str] = mapped_column(String(60))
    ativo: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
