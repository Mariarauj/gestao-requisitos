"""Engine e sessões do SQLAlchemy.

Este módulo não importa o Streamlit: assim, a camada de dados é testável sem a interface.
"""
from contextlib import contextmanager
from functools import lru_cache
from typing import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from sgr.config import get_database_url


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Engine único do processo (pool de conexões). Datas são gravadas em UTC."""
    return create_engine(
        get_database_url(),
        pool_pre_ping=True,
        connect_args={"options": "-c timezone=UTC"},
    )


@lru_cache(maxsize=1)
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


@contextmanager
def get_session() -> Iterator[Session]:
    """Sessão com commit ao final e rollback em caso de erro."""
    session = _session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
