"""Travas de transação para operações do tipo "conferir e gravar".

Algumas regras de unicidade não cabem numa restrição do banco: nomes de projeto e de épico são
únicos *sem diferenciar maiúsculas*, mas a restrição UNIQUE do banco só enxerga texto idêntico.
Sozinha, a checagem "já existe?" perde a corrida: duas requisições simultâneas, "Portal" e
"portal", não veem nada e as duas gravam. A trava abaixo serializa a sequência checar+gravar
dentro de um escopo (o proprietário, para projetos; o projeto, para épicos): quem chega depois
espera o commit de quem chegou antes e então já enxerga o nome. Escopos diferentes não se
bloqueiam. A trava vale até o fim da transação (commit ou rollback).
"""
from sqlalchemy import text
from sqlalchemy.orm import Session


def travar(session: Session, escopo: str, chave: int) -> None:
    """Pede a trava (bloqueando se outra transação a tem) do par escopo/chave."""
    session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"{escopo}:{chave}"})


def travar_nomes_de_projeto(session: Session, proprietario_id: int) -> None:
    travar(session, "nome-de-projeto", proprietario_id)


def travar_nomes_de_epico(session: Session, projeto_id: int) -> None:
    travar(session, "nome-de-epico", projeto_id)
