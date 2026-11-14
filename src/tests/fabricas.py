"""Cenário compartilhado pelos testes de histórias, épicos e critérios."""
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from sgr.services.criterio_service import CriterioService
from sgr.services.epico_service import EpicoService
from sgr.services.historia_service import HistoriaService


def um(conn, sql, **p):
    return conn.execute(text(sql), p).scalar_one()


def novo_usuario(conn, email):
    return um(conn, "INSERT INTO usuario (nome, email, senha_hash) VALUES ('U', :e, 'x') RETURNING id", e=email)


def novo_projeto(conn, dono, nome="P", com_product=True):
    pid = um(conn, "INSERT INTO projeto (nome, proprietario_id) VALUES (:n,:d) RETURNING id", n=nome, d=dono)
    conn.execute(text("INSERT INTO projeto_membro (projeto_id, usuario_id) VALUES (:p,:d)"), {"p": pid, "d": dono})
    product = None
    if com_product:
        product = um(conn, "INSERT INTO backlog (projeto_id, tipo, nome) VALUES (:p,'PRODUCT','Product Backlog') RETURNING id", p=pid)
    return pid, product


def auditoria(conn, entidade, operacao=None):
    sql = "SELECT entidade_id, operacao, valor_anterior, valor_posterior FROM registro_auditoria WHERE entidade = :e"
    if operacao:
        sql += " AND operacao = :o"
    return conn.execute(text(sql + " ORDER BY id"), {"e": entidade, "o": operacao}).all()


@pytest.fixture()
def cenario(conn):
    @contextmanager
    def sessao():
        s = Session(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    dono = novo_usuario(conn, "dono@x.com")
    outro = novo_usuario(conn, "outro@x.com")  # sem acesso ao projeto do dono
    projeto, product = novo_projeto(conn, dono)
    return SimpleNamespace(
        conn=conn, dono=dono, outro=outro, projeto=projeto, product=product,
        historias=HistoriaService(sessao), epicos=EpicoService(sessao), criterios=CriterioService(sessao),
    )


def criar_historia(c, **kw):
    dados = {"papel": "gerente de projetos", "acao": "cadastrar projetos", "beneficio": "organizar o trabalho"}
    dados.update(kw)
    return c.historias.criar(c.dono, c.projeto, **dados)
