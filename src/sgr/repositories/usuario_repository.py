from sqlalchemy import select
from sqlalchemy.orm import Session

from sgr.models import Usuario


def buscar_por_email(session: Session, email: str) -> Usuario | None:
    return session.scalar(select(Usuario).where(Usuario.email == email))


def criar(session: Session, nome: str, email: str, senha_hash: str) -> Usuario:
    usuario = Usuario(nome=nome, email=email, senha_hash=senha_hash)
    session.add(usuario)
    session.flush()  # materializa o id e dispara as restrições do banco (ex.: e-mail único)
    return usuario
