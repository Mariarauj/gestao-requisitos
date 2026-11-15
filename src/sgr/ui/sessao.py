"""Estado de autenticação da sessão do navegador (st.session_state).

Guarda o usuário (id, nome, e-mail) e os horários da sessão. A sessão expira por inatividade
(Storyboard 1, Q-06) e é perdida ao recarregar a página: limitação aceita no protótipo,
registrada no architecture notebook. Por isso não existe "Continuar conectado" (Q-01): ele
exigiria manter a sessão entre recargas, o que o framework de apresentação não faz sozinho.

Além do usuário, a sessão lembra *por que* a pessoa está vendo a tela de acesso, para mostrar a
mensagem certa: saiu por conta própria, a sessão expirou ou tentou abrir um endereço interno.
"""
from datetime import datetime, timedelta, timezone
from enum import Enum
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import streamlit as st

from sgr.services.auth_service import UsuarioAutenticado

TEMPO_DE_SESSAO = timedelta(hours=8)  # inatividade máxima

_USUARIO = "usuario_autenticado"
_INICIO = "sessao_iniciada_em"
_ATIVIDADE = "sessao_ultima_atividade"
_MOTIVO = "motivo_de_acesso"
_ULTIMO_EMAIL = "ultimo_email"

# Motivos para exibir a tela de acesso
ENTRAR, SAIU, EXPIRADA, SEM_SESSAO = "entrar", "saiu", "expirada", "sem_sessao"


class EstadoSessao(Enum):
    ATIVA = "ativa"
    AUSENTE = "ausente"
    EXPIRADA = "expirada"


def agora() -> datetime:
    """Relógio da sessão (UTC). Os testes o substituem para simular o passar do tempo."""
    return datetime.now(timezone.utc)


def horas_de_sessao() -> int:
    return int(TEMPO_DE_SESSAO.total_seconds() // 3600)


# ---------- usuário e ciclo da sessão ----------

def usuario_logado() -> UsuarioAutenticado | None:
    return st.session_state.get(_USUARIO)


def iniciar_sessao(usuario: UsuarioAutenticado) -> None:
    momento = agora()
    st.session_state[_USUARIO] = usuario
    st.session_state[_INICIO] = momento
    st.session_state[_ATIVIDADE] = momento
    st.session_state.pop(_MOTIVO, None)
    st.session_state.pop(_ULTIMO_EMAIL, None)


def encerrar_sessao(motivo: str = SAIU, ultimo_email: str | None = None) -> None:
    """Limpa todo o estado, inclusive campos de formulário, para não vazar dados entre usuários,
    e registra o motivo para a tela de acesso."""
    st.session_state.clear()
    st.session_state[_MOTIVO] = motivo
    if ultimo_email:
        st.session_state[_ULTIMO_EMAIL] = ultimo_email


def verificar_sessao() -> EstadoSessao:
    """Confere a sessão a cada execução de página (Q-06: o endereço digitado não contorna a
    autenticação). Atividade renova o prazo; passar de TEMPO_DE_SESSAO parado encerra a sessão."""
    usuario = usuario_logado()
    if usuario is None:
        return EstadoSessao.AUSENTE
    momento = agora()
    ultima = st.session_state.get(_ATIVIDADE)
    if ultima is None:  # usuário colocado no estado sem passar por iniciar_sessao
        st.session_state[_INICIO] = st.session_state[_ATIVIDADE] = momento
        return EstadoSessao.ATIVA
    if momento - ultima > TEMPO_DE_SESSAO:
        encerrar_sessao(EXPIRADA, ultimo_email=usuario.email)
        return EstadoSessao.EXPIRADA
    st.session_state[_ATIVIDADE] = momento
    return EstadoSessao.ATIVA


def exigir_login() -> UsuarioAutenticado:
    """Use no início de toda página protegida: interrompe a página se não houver sessão válida."""
    if verificar_sessao() is not EstadoSessao.ATIVA:
        st.error("Faça login para acessar esta página.")
        st.stop()
    return usuario_logado()


# ---------- por que a tela de acesso está aparecendo ----------

def motivo_de_acesso() -> str:
    return st.session_state.get(_MOTIVO, ENTRAR)


def definir_motivo(motivo: str) -> None:
    st.session_state[_MOTIVO] = motivo


def ultimo_email() -> str | None:
    return st.session_state.get(_ULTIMO_EMAIL)


def esquecer_ultimo_email() -> None:
    st.session_state.pop(_ULTIMO_EMAIL, None)


def caminho_da_url(url: str | None) -> str:
    """'http://host:8501/projetos?x=1' -> 'projetos'; a raiz vira ''."""
    if not url:
        return ""
    return urlparse(url).path.strip("/")


def caminho_solicitado() -> str:
    try:
        return caminho_da_url(st.context.url)
    except Exception:  # noqa: BLE001 - fora de uma requisição real (testes) não há URL
        return ""


def registrar_acesso_direto(caminhos_protegidos: set[str]) -> None:
    """Na primeira vez que alguém sem sessão chega, decide a mensagem: se o endereço pedido é de
    uma página interna (Q-06 B), explica que é preciso entrar. Depois disso o motivo já está
    definido e não é reavaliado, senão o link do navegador voltaria a mostrar o aviso."""
    if _MOTIVO in st.session_state:
        return
    st.session_state[_MOTIVO] = SEM_SESSAO if caminho_solicitado() in caminhos_protegidos else ENTRAR


# ---------- horário exibido ----------

def _fuso():
    try:
        nome = st.context.timezone
        return ZoneInfo(nome) if nome else timezone.utc
    except Exception:  # noqa: BLE001 - sem requisição ou fuso desconhecido: UTC
        return timezone.utc


def texto_da_sessao() -> str:
    """'Sessão iniciada às 09:14 · expira após 8 horas de inatividade' (Q-05)."""
    inicio = st.session_state.get(_INICIO) or agora()
    hora = inicio.astimezone(_fuso()).strftime("%H:%M")
    return f"Sessão iniciada às {hora} · expira após {horas_de_sessao()} horas de inatividade"
