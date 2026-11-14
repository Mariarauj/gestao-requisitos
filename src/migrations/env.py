"""Ambiente do Alembic: usa a URL de sgr.config e os metadados dos modelos."""
from alembic import context
from sqlalchemy import create_engine, pool

import sgr.models  # noqa: F401  (registra as tabelas em Base.metadata)
from sgr.config import get_database_url
from sgr.db.base import Base

config = context.config
target_metadata = Base.metadata


def _url() -> str:
    # Os testes podem informar a URL via config.set_main_option("sqlalchemy.url", ...).
    return config.get_main_option("sqlalchemy.url") or get_database_url()


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
