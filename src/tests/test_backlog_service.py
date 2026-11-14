"""CRUD de backlogs (requisitos 5 e 6): regras de negócio contra o PostgreSQL real."""
from contextlib import contextmanager
from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from sgr.services.auth_service import ErroDeValidacao
from sgr.services.backlog_service import (
    BacklogNaoEncontrado,
    BacklogService,
    ProductBacklogComHistorias,
    ProductBacklogJaExiste,
    SemProductBacklog,
)
from sgr.services.projeto_service import ProjetoNaoEncontrado

D = date


@pytest.fixture()
def servico(conn):
    """BacklogService ligado à transação do teste: commits viram savepoints, tudo é revertido."""

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

    return BacklogService(sessao)


def _um(conn, sql, **p):
    return conn.execute(text(sql), p).scalar_one()


def _usuario(conn, email):
    return _um(conn, "INSERT INTO usuario (nome, email, senha_hash) VALUES ('U', :e, 'x') RETURNING id", e=email)


def _projeto(conn, dono, nome="P"):
    pid = _um(conn, "INSERT INTO projeto (nome, proprietario_id) VALUES (:n,:d) RETURNING id", n=nome, d=dono)
    conn.execute(text("INSERT INTO projeto_membro (projeto_id, usuario_id) VALUES (:p,:d)"), {"p": pid, "d": dono})
    return pid


def _historia(conn, projeto, backlog, codigo, pts=3, **extra):
    cols = {"projeto_id": projeto, "backlog_id": backlog, "codigo": codigo, "papel": "gerente", "acao": "agir",
            "beneficio": "ganhar", "moscow": "M", "story_points": pts, **extra}
    return _um(conn, f"INSERT INTO historia ({', '.join(cols)}) VALUES ({', '.join(':' + c for c in cols)}) RETURNING id", **cols)


@pytest.fixture()
def ana(conn):
    return _usuario(conn, "ana@x.com")


@pytest.fixture()
def beto(conn):
    return _usuario(conn, "beto@x.com")


@pytest.fixture()
def proj(conn, ana):
    return _projeto(conn, ana)


def _auditoria(conn, entidade, operacao):
    return conn.execute(
        text("SELECT usuario_id, entidade_id, valor_anterior, valor_posterior FROM registro_auditoria "
             "WHERE entidade=:e AND operacao=:o ORDER BY id"), {"e": entidade, "o": operacao}).all()


# ---------- product backlog ----------

def test_criar_product_backlog(servico, ana, proj, conn):
    b = servico.criar_product(ana, proj, " Product Backlog ", " O que reúne ")
    assert (b.tipo, b.nome, b.descricao, b.estado, b.data_inicio, b.data_fim) == ("PRODUCT", "Product Backlog", "O que reúne", None, None, None)
    assert (b.historias, b.pontos) == (0, 0)
    (aud,) = _auditoria(conn, "backlog", "CRIAR")
    assert aud.usuario_id == ana and aud.entidade_id == b.id and aud.valor_posterior["tipo"] == "PRODUCT"


def test_so_um_product_backlog_por_projeto(servico, ana, proj, conn):
    servico.criar_product(ana, proj, "PB")
    with pytest.raises(ProductBacklogJaExiste) as e:
        servico.criar_product(ana, proj, "Outro")
    assert "crie um novo projeto" in str(e.value)
    assert servico.listar(ana, proj).product.nome == "PB"
    outro = _projeto(conn, ana, "Outro projeto")
    servico.criar_product(ana, outro, "PB")  # cada projeto tem o seu


def test_product_backlog_validacao(servico, ana, proj):
    with pytest.raises(ErroDeValidacao) as e:
        servico.criar_product(ana, proj, "  ", "d" * 281)
    assert set(e.value.erros) == {"nome", "descricao"}
    with pytest.raises(ErroDeValidacao):
        servico.criar_product(ana, proj, "n" * 121)
    assert servico.listar(ana, proj).product is None


def test_atualizar_product(servico, ana, proj, conn):
    b = servico.criar_product(ana, proj, "PB", "d")
    novo = servico.atualizar(ana, b.id, "Principal", None)
    assert (novo.nome, novo.descricao) == ("Principal", None)
    (aud,) = _auditoria(conn, "backlog", "ALTERAR")
    assert aud.valor_anterior["nome"] == "PB" and aud.valor_posterior["nome"] == "Principal"


def test_atualizar_sem_mudancas_nao_audita(servico, ana, proj, conn):
    b = servico.criar_product(ana, proj, "PB", "d")
    servico.atualizar(ana, b.id, "PB", "d")
    assert _auditoria(conn, "backlog", "ALTERAR") == []


def test_excluir_product_vazio(servico, ana, proj, conn):
    b = servico.criar_product(ana, proj, "PB")
    assert servico.excluir(ana, b.id) == 0
    assert servico.listar(ana, proj).product is None
    servico.criar_product(ana, proj, "PB de novo")  # liberou a vaga
    assert len(_auditoria(conn, "backlog", "EXCLUIR")) == 1


def test_nao_exclui_product_com_historias(servico, ana, proj, conn):
    b = servico.criar_product(ana, proj, "PB")
    _historia(conn, proj, b.id, "H-1")
    _historia(conn, proj, b.id, "H-2")
    with pytest.raises(ProductBacklogComHistorias) as e:
        servico.excluir(ana, b.id)
    assert e.value.quantidade == 2 and "2 histórias dependem dele" in str(e.value)
    assert servico.obter(ana, b.id).historias == 2
    assert _auditoria(conn, "backlog", "EXCLUIR") == []


# ---------- sprint backlog ----------

def test_criar_sprint(servico, ana, proj, conn):
    s = servico.criar_sprint(ana, proj, " Sprint 13 ", D(2026, 10, 15), D(2026, 10, 28), " Entregar login ")
    assert (s.tipo, s.nome, s.descricao, s.estado) == ("SPRINT", "Sprint 13", "Entregar login", "PLANEJADO")
    assert (s.data_inicio, s.data_fim, s.duracao_dias) == (D(2026, 10, 15), D(2026, 10, 28), 14)
    (aud,) = _auditoria(conn, "backlog", "CRIAR")
    assert aud.valor_posterior["data_inicio"] == "2026-10-15" and aud.valor_posterior["estado"] == "PLANEJADO"


def test_varios_sprints_sao_permitidos(servico, ana, proj):
    for i in range(1, 4):
        servico.criar_sprint(ana, proj, f"Sprint {i}", D(2026, i, 1), D(2026, i, 14))
    assert len(servico.listar(ana, proj).sprints) == 3
    assert servico.sugerir_nome_sprint(ana, proj) == "Sprint 4"


def test_sprint_exige_nome_e_datas_com_fim_posterior(servico, ana, proj):
    with pytest.raises(ErroDeValidacao) as e:
        servico.criar_sprint(ana, proj, "", None, None)
    assert set(e.value.erros) == {"nome", "data_inicio", "data_fim"}
    for fim in (D(2026, 10, 14), D(2026, 10, 15)):  # antes e igual ao início
        with pytest.raises(ErroDeValidacao) as e:
            servico.criar_sprint(ana, proj, "S", D(2026, 10, 15), fim)
        assert e.value.erros == {"data_fim": "A data de fim deve ser posterior à data de início."}
    assert servico.listar(ana, proj).sprints == []


def test_listar_ordena_sprints_do_mais_recente_e_traz_contagens(servico, ana, proj, conn):
    pb = servico.criar_product(ana, proj, "PB")
    velho = servico.criar_sprint(ana, proj, "Velho", D(2026, 1, 1), D(2026, 1, 14))
    novo = servico.criar_sprint(ana, proj, "Novo", D(2026, 3, 1), D(2026, 3, 14))
    _historia(conn, proj, pb.id, "H-1", 5)
    _historia(conn, proj, pb.id, "H-2", 8)
    _historia(conn, proj, novo.id, "H-3", 2)
    r = servico.listar(ana, proj)
    assert [s.nome for s in r.sprints] == ["Novo", "Velho"]
    assert (r.product.historias, r.product.pontos) == (2, 13)
    assert (r.sprints[0].historias, r.sprints[0].pontos) == (1, 2)
    assert (r.sprints[1].historias, r.sprints[1].pontos) == (0, 0)


def test_atualizar_sprint_preserva_estado_e_historias(servico, ana, proj, conn):
    s = servico.criar_sprint(ana, proj, "S", D(2026, 10, 15), D(2026, 10, 28))
    conn.execute(text("UPDATE backlog SET estado='EM_ANDAMENTO' WHERE id=:i"), {"i": s.id})
    _historia(conn, proj, s.id, "H-1")
    novo = servico.atualizar(ana, s.id, "Sprint 13", "Meta", D(2026, 10, 16), D(2026, 10, 30))
    assert (novo.nome, novo.descricao, novo.data_inicio, novo.data_fim) == ("Sprint 13", "Meta", D(2026, 10, 16), D(2026, 10, 30))
    assert novo.estado == "EM_ANDAMENTO" and novo.historias == 1
    with pytest.raises(ErroDeValidacao):  # a regra das datas vale também na edição
        servico.atualizar(ana, s.id, "Sprint 13", None, D(2026, 10, 16), D(2026, 10, 10))
    assert servico.obter(ana, s.id).data_fim == D(2026, 10, 30)


def test_excluir_sprint_devolve_historias_ao_product_backlog(servico, ana, proj, conn):
    pb = servico.criar_product(ana, proj, "PB")
    s = servico.criar_sprint(ana, proj, "S13", D(2026, 10, 15), D(2026, 10, 28))
    h = _historia(conn, proj, s.id, "SGR-1", 5, rice_reach=10, rice_impact=2, rice_confidence=80, rice_effort=3)
    conn.execute(text("INSERT INTO criterio_aceitacao (historia_id, contexto, acao, resultado, ordem) VALUES (:h,'c','a','r',1)"), {"h": h})

    assert servico.excluir(ana, s.id) == 1

    assert servico.listar(ana, proj).sprints == []
    linha = conn.execute(text("SELECT backlog_id, codigo, story_points, moscow, rice_reach FROM historia WHERE id=:h"), {"h": h}).one()
    assert tuple(linha) == (pb.id, "SGR-1", 5, "M", 10)  # nada foi perdido
    assert _um(conn, "SELECT count(*) FROM criterio_aceitacao WHERE historia_id=:h", h=h) == 1
    assert servico.obter(ana, pb.id).historias == 1
    (mov,) = _auditoria(conn, "historia", "ALTERAR")
    assert mov.entidade_id == h and mov.valor_anterior == {"backlog_id": s.id} and mov.valor_posterior == {"backlog_id": pb.id}
    (exc,) = _auditoria(conn, "backlog", "EXCLUIR")
    assert exc.valor_anterior["historias"] == 1


def test_excluir_sprint_vazio_nao_exige_product_backlog(servico, ana, proj):
    s = servico.criar_sprint(ana, proj, "S", D(2026, 1, 1), D(2026, 1, 14))
    assert servico.excluir(ana, s.id) == 0


def test_excluir_sprint_com_historias_sem_product_backlog_e_recusado(servico, ana, proj, conn):
    s = servico.criar_sprint(ana, proj, "S", D(2026, 1, 1), D(2026, 1, 14))
    _historia(conn, proj, s.id, "H-1")
    with pytest.raises(SemProductBacklog):
        servico.excluir(ana, s.id)
    assert servico.obter(ana, s.id).historias == 1  # nada mudou


# ---------- acesso ----------

def test_projeto_alheio_e_tratado_como_inexistente(servico, ana, beto, proj):
    s = servico.criar_sprint(ana, proj, "S", D(2026, 1, 1), D(2026, 1, 14))
    with pytest.raises(ProjetoNaoEncontrado):
        servico.listar(beto, proj)
    with pytest.raises(ProjetoNaoEncontrado):
        servico.criar_product(beto, proj, "PB")
    with pytest.raises(ProjetoNaoEncontrado):
        servico.criar_sprint(beto, proj, "S", D(2026, 1, 1), D(2026, 1, 14))
    for operacao in (lambda: servico.obter(beto, s.id), lambda: servico.atualizar(beto, s.id, "X", None, D(2026, 1, 1), D(2026, 1, 14)),
                     lambda: servico.excluir(beto, s.id), lambda: servico.listar_historias(beto, s.id)):
        with pytest.raises(BacklogNaoEncontrado):
            operacao()
    assert servico.obter(ana, s.id).nome == "S"


def test_membro_gerencia_os_backlogs_do_projeto(servico, ana, beto, proj, conn):
    conn.execute(text("INSERT INTO projeto_membro (projeto_id, usuario_id) VALUES (:p,:u)"), {"p": proj, "u": beto})
    pb = servico.criar_product(beto, proj, "PB")
    servico.atualizar(beto, pb.id, "PB 2", None)
    assert servico.listar(ana, proj).product.nome == "PB 2"
    servico.excluir(beto, pb.id)


def test_listar_historias_do_backlog(servico, ana, proj, conn):
    pb = servico.criar_product(ana, proj, "PB")
    _historia(conn, proj, pb.id, "H-2", 5)
    _historia(conn, proj, pb.id, "H-1", None)
    h = servico.listar_historias(ana, pb.id)
    assert [(x.codigo, x.story_points, x.moscow) for x in h] == [("H-2", 5, "M"), ("H-1", None, "M")]
