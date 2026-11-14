"""Informações de diagnóstico do sistema."""
from sqlalchemy import inspect, text

from sgr.db import get_engine


def tabelas_do_banco() -> list[str]:
    """Testa a conexão e devolve as tabelas do sistema (sem a tabela de controle do Alembic)."""
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return sorted(t for t in inspect(engine).get_table_names() if t != "alembic_version")
