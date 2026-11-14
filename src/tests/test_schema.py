"""Verifica se o banco criado pelas migrations cumpre o projeto físico (artefato 7)."""
import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

import sgr.models  # noqa: F401
from sgr.db.base import Base
from tests.conftest import _alembic_config

TABELAS = {
    "usuario", "projeto", "projeto_membro", "backlog", "historia",
    "criterio_aceitacao", "epico", "epico_historia", "registro_auditoria",
}


# ---------- estrutura ----------

def test_cria_as_nove_tabelas(engine):
    assert set(inspect(engine).get_table_names()) - {"alembic_version"} == TABELAS


def test_migration_e_modelos_estao_alinhados(engine):
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []


def test_nomes_das_check_constraints_coincidem_com_os_modelos(engine):
    with engine.connect() as conn:
        no_banco = {
            r[0] for r in conn.execute(text("SELECT conname FROM pg_constraint WHERE contype = 'c' AND connamespace = 'public'::regnamespace"))
        }
    nos_modelos = {
        c.name
        for t in Base.metadata.tables.values()
        for c in t.constraints
        if c.__class__.__name__ == "CheckConstraint"
    }
    assert no_banco == nos_modelos


def test_downgrade_remove_tudo_e_upgrade_recria(engine, test_url):
    config = _alembic_config(test_url)
    command.downgrade(config, "base")
    assert set(inspect(engine).get_table_names()) - {"alembic_version"} == set()
    command.upgrade(config, "head")
    assert set(inspect(engine).get_table_names()) - {"alembic_version"} == TABELAS


# ---------- helpers de dados ----------

def _um(conn, sql, **params):
    return conn.execute(text(sql), params).scalar_one()


def _usuario(conn, email="a@x.com"):
    return _um(conn, "INSERT INTO usuario (nome, email, senha_hash) VALUES ('A', :e, :h) RETURNING id",
               e=email, h="x" * 60)


def _projeto(conn, dono, nome="P"):
    return _um(conn, "INSERT INTO projeto (nome, proprietario_id) VALUES (:n, :d) RETURNING id",
               n=nome, d=dono)


def _product(conn, projeto, nome="Product"):
    return _um(conn, "INSERT INTO backlog (projeto_id, tipo, nome) VALUES (:p, 'PRODUCT', :n) RETURNING id",
               p=projeto, n=nome)


def _sprint(conn, projeto, nome="Sprint 1"):
    return _um(conn, "INSERT INTO backlog (projeto_id, tipo, nome, data_inicio, data_fim, estado) "
                     "VALUES (:p, 'SPRINT', :n, '2026-11-16', '2026-11-30', 'PLANEJADO') RETURNING id",
               p=projeto, n=nome)


def _historia(conn, projeto, backlog, codigo="SGR-1", **extra):
    cols = {"projeto_id": projeto, "backlog_id": backlog, "codigo": codigo, "papel": "gerente",
            "acao": "criar projetos", "beneficio": "organizar o trabalho", "moscow": "M", **extra}
    nomes = ", ".join(cols)
    valores = ", ".join(f":{c}" for c in cols)
    return _um(conn, f"INSERT INTO historia ({nomes}) VALUES ({valores}) RETURNING id", **cols)


@pytest.fixture()
def base(conn):
    dono = _usuario(conn)
    projeto = _projeto(conn, dono)
    return conn, dono, projeto, _product(conn, projeto)


def _falha(conn, sql, **params):
    """Executa o SQL esperando violação de integridade, sem invalidar a transação do teste."""
    with pytest.raises(IntegrityError):
        with conn.begin_nested():
            conn.execute(text(sql), params)


# ---------- backlogs ----------

def test_apenas_um_product_backlog_por_projeto(base):
    conn, _, projeto, _ = base
    _falha(conn, "INSERT INTO backlog (projeto_id, tipo, nome) VALUES (:p, 'PRODUCT', 'Outro')", p=projeto)


def test_varios_sprint_backlogs_por_projeto(base):
    conn, _, projeto, _ = base
    _sprint(conn, projeto, "Sprint 1")
    _sprint(conn, projeto, "Sprint 2")


def test_product_backlog_nao_aceita_periodo(base):
    conn, _, projeto, _ = base
    p2 = _projeto(conn, base[1], "P2")
    _falha(conn, "INSERT INTO backlog (projeto_id, tipo, nome, data_inicio) VALUES (:p, 'PRODUCT', 'x', '2026-11-16')", p=p2)


def test_sprint_exige_periodo_e_fim_maior_que_inicio(base):
    conn, _, projeto, _ = base
    _falha(conn, "INSERT INTO backlog (projeto_id, tipo, nome) VALUES (:p, 'SPRINT', 'x')", p=projeto)
    _falha(conn, "INSERT INTO backlog (projeto_id, tipo, nome, data_inicio, data_fim, estado) "
                 "VALUES (:p, 'SPRINT', 'x', '2026-11-30', '2026-11-16', 'PLANEJADO')", p=projeto)


# ---------- história: domínios ----------

@pytest.mark.parametrize("pontos", [0, 1, 2, 3, 5, 8, 13, 21, 34, 55])
def test_story_points_validos(base, pontos):
    conn, _, projeto, product = base
    _historia(conn, projeto, product, story_points=pontos)


@pytest.mark.parametrize("pontos", [4, 7, 10, 56, -1])
def test_story_points_invalidos(base, pontos):
    conn, _, projeto, product = base
    with pytest.raises(IntegrityError):
        with conn.begin_nested():
            _historia(conn, projeto, product, story_points=pontos)


def test_moscow_invalido_e_obrigatorio(base):
    conn, _, projeto, product = base
    with pytest.raises(IntegrityError):
        with conn.begin_nested():
            _historia(conn, projeto, product, moscow="X")
    _falha(conn, "INSERT INTO historia (projeto_id, backlog_id, codigo, papel, acao, beneficio) "
                 "VALUES (:p, :b, 'SGR-9', 'a', 'b', 'c')", p=projeto, b=product)


def test_rice_valido_e_calculavel(base):
    conn, _, projeto, product = base
    h = _historia(conn, projeto, product, rice_reach=100, rice_impact=0.5,
                  rice_confidence=80, rice_effort=5)
    score = _um(conn, "SELECT (rice_reach * rice_impact * rice_confidence / 100.0) / rice_effort "
                      "FROM historia WHERE id = :i", i=h)
    assert float(score) == 8.0


@pytest.mark.parametrize("campo,valor", [
    ("rice_impact", 4), ("rice_confidence", 90), ("rice_effort", 0), ("rice_effort", 4), ("rice_reach", -1),
])
def test_rice_valores_invalidos(base, campo, valor):
    conn, _, projeto, product = base
    completo = {"rice_reach": 10, "rice_impact": 1, "rice_confidence": 100, "rice_effort": 3}
    completo[campo] = valor
    with pytest.raises(IntegrityError):
        with conn.begin_nested():
            _historia(conn, projeto, product, **completo)


def test_rice_parcial_e_recusado(base):
    conn, _, projeto, product = base
    with pytest.raises(IntegrityError):
        with conn.begin_nested():
            _historia(conn, projeto, product, rice_reach=10)


def test_codigo_unico_por_projeto(base):
    conn, dono, projeto, product = base
    _historia(conn, projeto, product, codigo="SGR-1")
    with pytest.raises(IntegrityError):
        with conn.begin_nested():
            _historia(conn, projeto, product, codigo="SGR-1")
    p2 = _projeto(conn, dono, "P2")
    _historia(conn, p2, _product(conn, p2), codigo="SGR-1")


# ---------- movimentação e exclusões ----------

def test_mover_historia_entre_backlogs_preserva_dados(base):
    conn, _, projeto, product = base
    sprint = _sprint(conn, projeto)
    h = _historia(conn, projeto, product, story_points=5)
    conn.execute(text("INSERT INTO criterio_aceitacao (historia_id, contexto, acao, resultado, ordem) "
                      "VALUES (:h, 'c', 'a', 'r', 1)"), {"h": h})
    conn.execute(text("UPDATE historia SET backlog_id = :b WHERE id = :h"), {"b": sprint, "h": h})
    row = conn.execute(text("SELECT codigo, story_points, backlog_id FROM historia WHERE id = :h"), {"h": h}).one()
    assert (row.codigo, row.story_points, row.backlog_id) == ("SGR-1", 5, sprint)
    assert _um(conn, "SELECT count(*) FROM criterio_aceitacao WHERE historia_id = :h", h=h) == 1


def test_backlog_com_historias_nao_pode_ser_excluido(base):
    conn, _, projeto, product = base
    _historia(conn, projeto, product)
    _falha(conn, "DELETE FROM backlog WHERE id = :b", b=product)


def test_epico_com_historias_nao_pode_ser_excluido(base):
    conn, _, projeto, product = base
    h = _historia(conn, projeto, product)
    e = _um(conn, "INSERT INTO epico (projeto_id, nome) VALUES (:p, 'E') RETURNING id", p=projeto)
    conn.execute(text("INSERT INTO epico_historia (epico_id, historia_id) VALUES (:e, :h)"), {"e": e, "h": h})
    _falha(conn, "DELETE FROM epico WHERE id = :e", e=e)


def test_excluir_historia_remove_criterios_e_vinculos(base):
    conn, _, projeto, product = base
    h = _historia(conn, projeto, product)
    e = _um(conn, "INSERT INTO epico (projeto_id, nome) VALUES (:p, 'E') RETURNING id", p=projeto)
    conn.execute(text("INSERT INTO epico_historia (epico_id, historia_id) VALUES (:e, :h)"), {"e": e, "h": h})
    conn.execute(text("INSERT INTO criterio_aceitacao (historia_id, contexto, acao, resultado, ordem) "
                      "VALUES (:h, 'c', 'a', 'r', 1)"), {"h": h})
    conn.execute(text("DELETE FROM historia WHERE id = :h"), {"h": h})
    assert _um(conn, "SELECT count(*) FROM criterio_aceitacao") == 0
    assert _um(conn, "SELECT count(*) FROM epico_historia") == 0
    assert _um(conn, "SELECT count(*) FROM epico WHERE id = :e", e=e) == 1


def test_criterio_ordem_unica_por_historia(base):
    conn, _, projeto, product = base
    h = _historia(conn, projeto, product)
    sql = "INSERT INTO criterio_aceitacao (historia_id, contexto, acao, resultado, ordem) VALUES (:h, 'c', 'a', 'r', 1)"
    conn.execute(text(sql), {"h": h})
    _falha(conn, sql, h=h)


def test_excluir_projeto_remove_backlogs_historias_epicos(base):
    conn, _, projeto, product = base
    _historia(conn, projeto, product)
    conn.execute(text("INSERT INTO epico (projeto_id, nome) VALUES (:p, 'E')"), {"p": projeto})
    conn.execute(text("DELETE FROM projeto WHERE id = :p"), {"p": projeto})
    for tabela in ("backlog", "historia", "epico"):
        assert _um(conn, f"SELECT count(*) FROM {tabela}") == 0


def test_usuario_com_projetos_nao_pode_ser_excluido_e_email_e_unico(base):
    conn, dono, _, _ = base
    _falha(conn, "DELETE FROM usuario WHERE id = :u", u=dono)
    _falha(conn, "INSERT INTO usuario (nome, email, senha_hash) VALUES ('B', 'a@x.com', :h)", h="x" * 60)


def test_auditoria_sobrevive_a_exclusao_do_autor(conn):
    u = _usuario(conn, "autor@x.com")
    r = _um(conn, "INSERT INTO registro_auditoria (usuario_id, entidade, entidade_id, operacao) "
                  "VALUES (:u, 'projeto', 1, 'CRIAR') RETURNING id", u=u)
    conn.execute(text("DELETE FROM usuario WHERE id = :u"), {"u": u})
    assert _um(conn, "SELECT usuario_id FROM registro_auditoria WHERE id = :r", r=r) is None
    _falha(conn, "INSERT INTO registro_auditoria (entidade, entidade_id, operacao) VALUES ('invalida', 1, 'CRIAR')")
