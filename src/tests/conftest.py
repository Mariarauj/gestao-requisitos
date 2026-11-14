"""Fixtures dos testes de banco.

Usam um PostgreSQL real, indicado por TEST_DATABASE_URL. ATENÇÃO: o schema public desse
banco é APAGADO e recriado a cada execução. Sem TEST_DATABASE_URL, os testes são ignorados.
"""
import os

import pytest
from alembic import command
from alembic.config import Config
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()


def _alembic_config(url: str) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


@pytest.fixture(scope="session")
def test_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL não definida")
    return url


@pytest.fixture(scope="session")
def engine(test_url):
    eng = create_engine(test_url)
    with eng.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    command.upgrade(_alembic_config(test_url), "head")
    yield eng
    eng.dispose()


@pytest.fixture()
def conn(engine):
    """Conexão com transação revertida ao final de cada teste."""
    with engine.connect() as connection:
        transaction = connection.begin()
        yield connection
        transaction.rollback()
