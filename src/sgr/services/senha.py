"""Regra de senha e medidor de força (Storyboard 1, quadros Q-02 e Q-03).

A regra mora aqui, num só lugar: o serviço de cadastro a impõe e a tela usa o mesmo cálculo
para mostrar os critérios enquanto a pessoa digita, de modo que os dois nunca discordam.

Regra: no mínimo 8 caracteres, com pelo menos uma letra e um número.
Força: "fraca" se a regra não é atendida; "boa" se atendida; "forte" se, além disso, tem 12 ou
mais caracteres e mistura maiúsculas e minúsculas ou usa algum símbolo.
"""
from __future__ import annotations

from dataclasses import dataclass

SENHA_MIN = 8
FORTE_MIN = 12

MENSAGEM_REGRA = "A senha precisa ter pelo menos 8 caracteres, uma letra e um número."


@dataclass(frozen=True)
class Criterio:
    texto: str
    atendido: bool


@dataclass(frozen=True)
class AvaliacaoSenha:
    criterios: tuple[Criterio, ...]
    nivel: str  # "vazia", "fraca", "boa" ou "forte"

    @property
    def atende(self) -> bool:
        return all(c.atendido for c in self.criterios)


def avaliar_senha(senha: str | None) -> AvaliacaoSenha:
    senha = senha or ""
    criterios = (
        Criterio(f"mínimo {SENHA_MIN} caracteres", len(senha) >= SENHA_MIN),
        Criterio("uma letra", any(c.isalpha() for c in senha)),
        Criterio("um número", any(c.isdecimal() for c in senha)),
    )
    if not senha:
        return AvaliacaoSenha(criterios, "vazia")
    if not all(c.atendido for c in criterios):
        return AvaliacaoSenha(criterios, "fraca")
    mistura = any(c.isupper() for c in senha) and any(c.islower() for c in senha)
    simbolo = any(not c.isalnum() and not c.isspace() for c in senha)
    forte = len(senha) >= FORTE_MIN and (mistura or simbolo)
    return AvaliacaoSenha(criterios, "forte" if forte else "boa")
