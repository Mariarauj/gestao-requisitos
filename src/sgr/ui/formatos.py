"""Formatação de texto compartilhada pelas telas de backlog."""
from datetime import date
from decimal import Decimal

ESTADOS = {"PLANEJADO": "Planejado", "EM_ANDAMENTO": "Em andamento", "ENCERRADO": "Encerrado"}
MOSCOW_NOMES = {"M": "Must have", "S": "Should have", "C": "Could have", "W": "Won't have"}


def plural(n: int, singular: str, plural_: str) -> str:
    return f"{n} {singular if n <= 1 else plural_}"


def data(d: date | None) -> str:
    return d.strftime("%d/%m/%Y") if d else ""


def nota(valor: Decimal) -> str:
    """Nota RICE sem zeros à direita e com vírgula decimal: 32.00 -> 32; 0.04 -> 0,04."""
    return format(valor.normalize(), "f").replace(".", ",")
