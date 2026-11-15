"""Domínios fechados e cálculo da pontuação RICE (requisitos 17 a 19).

Este módulo não conhece banco nem interface: a fórmula existe aqui, e somente aqui, para
não divergir entre telas. Única exceção: a listagem de histórias filtra e ordena por RICE no
banco e repete a conta em SQL (historia_repository.rice_sql); tests/test_rice_listagem.py
compara as duas em todo o domínio e falha se divergirem.

    RICE = (Reach × Impact × Confidence) / Effort

- Reach: número de usuários atingidos (inteiro, 0 ou mais);
- Impact: 3, 2, 1, 0.5 ou 0.25;
- Confidence: 100, 80 ou 50, tratado como percentual (divide por 100);
- Effort: valor da escala de story points, exceto o zero (divisão por zero). O banco recusa
  o zero nessa coluna pela mesma razão.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from sgr.services.auth_service import ErroDeValidacao

IMPACTOS = (Decimal("3"), Decimal("2"), Decimal("1"), Decimal("0.5"), Decimal("0.25"))
CONFIANCAS = (100, 80, 50)
ESFORCOS = (1, 2, 3, 5, 8, 13, 21, 34, 55)

_CENTAVOS = Decimal("0.01")


def _texto(valores) -> str:
    return ", ".join(format(v.normalize(), "f") if isinstance(v, Decimal) else str(v) for v in valores)


def _inteiro(valor) -> int | None:
    """Aceita int, ou Decimal/float com valor inteiro (o que a interface possa enviar)."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor
    if isinstance(valor, (float, Decimal)):
        try:
            return int(valor) if valor == int(valor) else None
        except (ValueError, OverflowError):  # NaN, infinito
            return None
    return None


def _decimal(valor) -> Decimal | None:
    if isinstance(valor, bool) or valor is None:
        return None
    try:
        return Decimal(str(valor).strip().replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def validar_rice(reach, impact, confidence, effort) -> tuple[int, Decimal, int, int]:
    """Valida as quatro entradas e as devolve normalizadas.

    Levanta ErroDeValidacao com uma mensagem por campo inválido (chaves: rice_reach,
    rice_impact, rice_confidence e rice_effort). As quatro entradas são obrigatórias:
    não existe RICE parcial.
    """
    erros: dict[str, str] = {}

    r = _inteiro(reach)
    if reach is None:
        erros["rice_reach"] = "Informe o Reach (número de usuários)."
    elif r is None or r < 0:
        erros["rice_reach"] = "Reach inválido. Informe um número inteiro maior ou igual a 0."

    i = _decimal(impact)
    if impact is None:
        erros["rice_impact"] = "Informe o Impact."
    elif i not in IMPACTOS:
        erros["rice_impact"] = f"Impact inválido. Valores aceitos: {_texto(IMPACTOS)}."

    c = _inteiro(confidence)
    if confidence is None:
        erros["rice_confidence"] = "Informe o Confidence."
    elif c not in CONFIANCAS:
        erros["rice_confidence"] = f"Confidence inválido. Valores aceitos: {_texto(CONFIANCAS)} (%)."

    e = _inteiro(effort)
    if effort is None:
        erros["rice_effort"] = "Informe o Effort."
    elif e not in ESFORCOS:
        erros["rice_effort"] = f"Effort inválido. Valores aceitos: {_texto(ESFORCOS)}."

    if erros:
        raise ErroDeValidacao(erros)
    return r, i, c, e


def calcular_rice(reach, impact, confidence, effort) -> Decimal:
    """Nota RICE com duas casas decimais (arredondamento comercial).

    Exemplo: Reach 1000, Impact 2, Confidence 80, Effort 5 → 1000 × 2 × 0,8 / 5 = 320,00.
    As entradas são validadas aqui também, para que a conta nunca rode com valor fora do
    domínio, qualquer que seja o chamador.
    """
    r, i, c, e = validar_rice(reach, impact, confidence, effort)
    return (Decimal(r) * i * Decimal(c) / Decimal(100 * e)).quantize(_CENTAVOS, ROUND_HALF_UP)
