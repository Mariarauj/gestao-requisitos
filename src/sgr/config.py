"""Configuração da aplicação, lida de variáveis de ambiente (ou do arquivo .env)."""
import os

from dotenv import load_dotenv

load_dotenv()

DEFAULT_DATABASE_URL = "postgresql+psycopg://sgr:sgr@localhost:5432/sgr"


def get_database_url() -> str:
    """URL de conexão com o PostgreSQL (driver psycopg 3)."""
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
