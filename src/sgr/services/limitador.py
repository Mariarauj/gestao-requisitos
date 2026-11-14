"""Limite de tentativas de login falhas, mantido em memória no processo."""
import math
import threading
import time
from collections import defaultdict, deque
from typing import Callable


class LimitadorTentativas:
    """Bloqueia uma chave (e-mail) após `max_falhas` falhas dentro de `janela_s` segundos.

    O estado fica na memória do processo e é perdido ao reiniciar o servidor; é suficiente
    para o protótipo e vale para todas as sessões do Streamlit, que compartilham o processo.
    """

    def __init__(
        self,
        max_falhas: int = 5,
        janela_s: int = 900,
        relogio: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max = max_falhas
        self._janela = janela_s
        self._relogio = relogio
        self._falhas: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _descartar_antigas(self, chave: str) -> deque[float]:
        falhas = self._falhas[chave]
        limite = self._relogio() - self._janela
        while falhas and falhas[0] <= limite:
            falhas.popleft()
        return falhas

    def segundos_restantes(self, chave: str) -> int:
        """Segundos até o desbloqueio; 0 se a chave não está bloqueada."""
        with self._lock:
            falhas = self._descartar_antigas(chave)
            if len(falhas) < self._max:
                return 0
            return max(1, math.ceil(falhas[0] + self._janela - self._relogio()))

    def registrar_falha(self, chave: str) -> None:
        with self._lock:
            self._descartar_antigas(chave).append(self._relogio())

    def limpar(self, chave: str) -> None:
        with self._lock:
            self._falhas.pop(chave, None)
