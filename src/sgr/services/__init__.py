"""Camada de negócio: regras do domínio (validações, cálculo RICE, movimentação de histórias)."""
from sgr.services.auth_service import AuthService
from sgr.services.backlog_service import BacklogService
from sgr.services.criterio_service import CriterioService
from sgr.services.epico_service import EpicoService
from sgr.services.historia_service import HistoriaService
from sgr.services.priorizacao_service import PriorizacaoService
from sgr.services.projeto_service import ProjetoService

# Instância compartilhada pela interface: o limitador de tentativas fica em memória no
# processo e precisa ser o mesmo para todas as sessões do Streamlit.
autenticacao = AuthService()
projetos = ProjetoService()
backlogs = BacklogService()
historias = HistoriaService()
epicos = EpicoService()
criterios = CriterioService()
priorizacao = PriorizacaoService()

__all__ = [
    "AuthService",
    "BacklogService",
    "CriterioService",
    "EpicoService",
    "HistoriaService",
    "PriorizacaoService",
    "ProjetoService",
    "autenticacao",
    "backlogs",
    "criterios",
    "epicos",
    "historias",
    "priorizacao",
    "projetos",
]
