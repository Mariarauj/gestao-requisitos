"""Camada de negócio: regras do domínio (validações, cálculo RICE, movimentação de histórias)."""
from sgr.services.auth_service import AuthService

# Instância compartilhada pela interface: o limitador de tentativas fica em memória no
# processo e precisa ser o mesmo para todas as sessões do Streamlit.
autenticacao = AuthService()

__all__ = ["AuthService", "autenticacao"]
