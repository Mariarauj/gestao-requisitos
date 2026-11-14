"""Camada de negócio: regras do domínio (validações, cálculo RICE, movimentação de histórias)."""
from sgr.services.auth_service import AuthService
from sgr.services.projeto_service import ProjetoService

# Instância compartilhada pela interface: o limitador de tentativas fica em memória no
# processo e precisa ser o mesmo para todas as sessões do Streamlit.
autenticacao = AuthService()
projetos = ProjetoService()

__all__ = ["AuthService", "ProjetoService", "autenticacao", "projetos"]
