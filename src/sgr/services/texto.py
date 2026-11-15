"""Texto que o banco não consegue guardar.

O PostgreSQL recusa o byte NUL (0x00) em colunas de texto, e um caractere "substituto"
isolado (como "\\ud800") não pode ser codificado em UTF-8. Qualquer um dos dois, se chegasse à
camada de dados, viraria DataError/UnicodeEncodeError e derrubaria a operação. Por isso toda
entrada de texto é conferida aqui, antes de qualquer acesso ao banco, e vira um erro de
validação do campo (ou, no login, "credenciais inválidas").
"""
from __future__ import annotations

MENSAGEM_CARACTERE_INVALIDO = "Este campo contém um caractere inválido."


def caractere_invalido(valor: str | None) -> bool:
    """True se o texto tem NUL ou um caractere que o UTF-8 não representa."""
    if not valor:
        return False
    if "\x00" in valor:
        return True
    try:
        valor.encode("utf-8")
    except UnicodeEncodeError:
        return True
    return False
