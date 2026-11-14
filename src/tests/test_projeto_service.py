"""CRUD de projetos (requisito 4): regras de negócio contra o PostgreSQL real."""
from contextlib import contextmanager

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from sgr.services.auth_service import ErroDeValidacao
from sgr.services.projeto_service import (
    NomeJaUsado,
    ProjetoNaoEncontrado,
    ProjetoService,
    SemPermissao,
)


@pytest.fixture()
def servico(conn):
    """ProjetoService ligado à transação do teste: commits viram savepoints, tudo é revertido."""

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

    return ProjetoService(sessao)


def _usuario(conn, email) -> int:
    return conn.execute(
        text("INSERT INTO usuario (nome, email, senha_hash) VALUES ('U', :e, 'x') RETURNING id"),
        {"e": email},
    ).scalar_one()


@pytest.fixture()
def ana(conn):
    return _usuario(conn, "ana@x.com")


@pytest.fixture()
def beto(conn):
    return _usuario(conn, "beto@x.com")


def _um(conn, sql, **p):
    return conn.execute(text(sql), p).scalar_one()


def _popular(conn, projeto_id):
    """1 product + 2 sprints, 2 histórias (3 + 5 pontos), 1 épico, 3 critérios."""
    produto = _um(conn, "INSERT INTO backlog (projeto_id, tipo, nome) VALUES (:p,'PRODUCT','PB') RETURNING id", p=projeto_id)
    for n in (1, 2):
        _um(conn, "INSERT INTO backlog (projeto_id, tipo, nome, data_inicio, data_fim, estado) "
                  "VALUES (:p,'SPRINT',:n,'2026-01-01','2026-01-15','PLANEJADO') RETURNING id", p=projeto_id, n=f"S{n}")
    ids = []
    for i, pts in enumerate((3, 5), start=1):
        ids.append(_um(conn, "INSERT INTO historia (projeto_id, backlog_id, codigo, papel, acao, beneficio, moscow, story_points) "
                             "VALUES (:p,:b,:c,'a','b','c','M',:s) RETURNING id", p=projeto_id, b=produto, c=f"H-{i}", s=pts))
    epico = _um(conn, "INSERT INTO epico (projeto_id, nome) VALUES (:p,'E') RETURNING id", p=projeto_id)
    conn.execute(text("INSERT INTO epico_historia (epico_id, historia_id) VALUES (:e,:h)"), {"e": epico, "h": ids[0]})
    for ordem in (1, 2):
        conn.execute(text("INSERT INTO criterio_aceitacao (historia_id, contexto, acao, resultado, ordem) VALUES (:h,'c','a','r',:o)"), {"h": ids[0], "o": ordem})
    conn.execute(text("INSERT INTO criterio_aceitacao (historia_id, contexto, acao, resultado, ordem) VALUES (:h,'c','a','r',1)"), {"h": ids[1]})


def _auditoria(conn, operacao):
    return conn.execute(
        text("SELECT usuario_id, entidade_id, valor_anterior, valor_posterior FROM registro_auditoria "
             "WHERE entidade='projeto' AND operacao=:o ORDER BY id"), {"o": operacao}).all()


# ---------- criar ----------

def test_criar_projeto(servico, ana, conn):
    p = servico.criar(ana, "  Portal do Cliente ", " Autosserviço ")
    assert (p.nome, p.descricao, p.proprietario_id, p.arquivado) == ("Portal do Cliente", "Autosserviço", ana, False)
    assert p.contagens.backlogs == 0  # o storyboard mostra "0 backlog" no projeto recém-criado
    membros = conn.execute(text("SELECT usuario_id FROM projeto_membro WHERE projeto_id=:p"), {"p": p.id}).scalars().all()
    assert membros == [ana]
    (aud,) = _auditoria(conn, "CRIAR")
    assert aud.usuario_id == ana and aud.entidade_id == p.id
    assert aud.valor_posterior == {"nome": "Portal do Cliente", "descricao": "Autosserviço"}


def test_descricao_vazia_vira_nulo(servico, ana):
    assert servico.criar(ana, "P", "   ").descricao is None


def test_nome_obrigatorio(servico, ana):
    for nome in ("", "   ", None):
        with pytest.raises(ErroDeValidacao) as e:
            servico.criar(ana, nome)
        assert e.value.erros == {"nome": "Informe o nome do projeto."}


def test_limites_de_tamanho(servico, ana):
    servico.criar(ana, "n" * 120, "d" * 280)  # no limite: aceita
    with pytest.raises(ErroDeValidacao) as e:
        servico.criar(ana, "n" * 121, "d" * 281)
    assert set(e.value.erros) == {"nome", "descricao"}


def test_nome_unico_por_proprietario_sem_diferenciar_maiusculas(servico, ana, beto):
    servico.criar(ana, "Portal")
    with pytest.raises(NomeJaUsado):
        servico.criar(ana, "portal")
    servico.criar(beto, "Portal")  # outro proprietário pode repetir


def test_falha_de_validacao_nao_grava_nem_audita(servico, ana, conn):
    with pytest.raises(ErroDeValidacao):
        servico.criar(ana, "")
    assert servico.listar(ana) == []
    assert _auditoria(conn, "CRIAR") == []


# ---------- ler ----------

def test_listar_ordenado_e_com_contagens(servico, ana, conn):
    b = servico.criar(ana, "beta")
    a = servico.criar(ana, "Alfa")
    _popular(conn, a.id)
    lista = servico.listar(ana)
    assert [p.nome for p in lista] == ["Alfa", "beta"]
    c = lista[0].contagens
    assert (c.product_backlogs, c.sprint_backlogs, c.backlogs) == (1, 2, 3)
    assert (c.historias, c.pontos, c.epicos, c.criterios) == (2, 8, 1, 3)
    assert lista[1].contagens.historias == 0


def test_listar_isola_usuarios_e_inclui_projetos_onde_e_membro(servico, ana, beto, conn):
    p_ana = servico.criar(ana, "Da Ana")
    servico.criar(beto, "Do Beto")
    assert [p.nome for p in servico.listar(ana)] == ["Da Ana"]
    conn.execute(text("INSERT INTO projeto_membro (projeto_id, usuario_id) VALUES (:p,:u)"), {"p": p_ana.id, "u": beto})
    assert [p.nome for p in servico.listar(beto)] == ["Da Ana", "Do Beto"]
    assert [p.nome for p in servico.listar(beto, apenas_meus=True)] == ["Do Beto"]


def test_busca_por_nome_trata_curingas_como_texto(servico, ana):
    servico.criar(ana, "Portal do Cliente")
    servico.criar(ana, "App de Campo")
    servico.criar(ana, "100%_real")
    assert [p.nome for p in servico.listar(ana, busca="  CLIENTE ")] == ["Portal do Cliente"]
    assert [p.nome for p in servico.listar(ana, busca="%")] == ["100%_real"]
    assert servico.listar(ana, busca="inexistente") == []


def test_filtro_de_arquivados(servico, ana, conn):
    p = servico.criar(ana, "Velho")
    servico.criar(ana, "Novo")
    conn.execute(text("UPDATE projeto SET arquivado = true WHERE id = :p"), {"p": p.id})
    assert [x.nome for x in servico.listar(ana)] == ["Novo"]
    assert [x.nome for x in servico.listar(ana, arquivados=True)] == ["Velho"]


def test_obter(servico, ana, beto, conn):
    p = servico.criar(ana, "P")
    _popular(conn, p.id)
    assert servico.obter(ana, p.id).contagens.historias == 2
    with pytest.raises(ProjetoNaoEncontrado):  # projeto de outro usuário = inexistente
        servico.obter(beto, p.id)
    with pytest.raises(ProjetoNaoEncontrado):
        servico.obter(ana, 999999)


# ---------- atualizar ----------

def test_atualizar_nome_e_descricao_preserva_o_conteudo(servico, ana, conn):
    p = servico.criar(ana, "Velho", "d1")
    _popular(conn, p.id)
    novo = servico.atualizar(ana, p.id, " Novo ", "d2")
    assert (novo.nome, novo.descricao) == ("Novo", "d2")
    assert novo.contagens.historias == 2 and novo.contagens.backlogs == 3
    (aud,) = _auditoria(conn, "ALTERAR")
    assert aud.valor_anterior == {"nome": "Velho", "descricao": "d1"}
    assert aud.valor_posterior == {"nome": "Novo", "descricao": "d2"}


def test_atualizar_sem_mudancas_nao_audita(servico, ana, conn):
    p = servico.criar(ana, "P", "d")
    servico.atualizar(ana, p.id, "P", "d")
    assert _auditoria(conn, "ALTERAR") == []


def test_atualizar_pode_manter_o_proprio_nome_e_mudar_so_a_descricao(servico, ana):
    p = servico.criar(ana, "P", "d")
    assert servico.atualizar(ana, p.id, "p", "outra").descricao == "outra"


def test_atualizar_para_nome_de_outro_projeto_falha(servico, ana):
    servico.criar(ana, "A")
    b = servico.criar(ana, "B")
    with pytest.raises(NomeJaUsado):
        servico.atualizar(ana, b.id, "a")
    assert servico.obter(ana, b.id).nome == "B"


def test_atualizar_valida_campos(servico, ana):
    p = servico.criar(ana, "P")
    with pytest.raises(ErroDeValidacao):
        servico.atualizar(ana, p.id, "")


def test_atualizar_exige_ser_proprietario(servico, ana, beto, conn):
    p = servico.criar(ana, "P")
    with pytest.raises(ProjetoNaoEncontrado):  # estranho: nem sabe que existe
        servico.atualizar(beto, p.id, "X")
    conn.execute(text("INSERT INTO projeto_membro (projeto_id, usuario_id) VALUES (:p,:u)"), {"p": p.id, "u": beto})
    with pytest.raises(SemPermissao):  # membro: vê, mas não altera
        servico.atualizar(beto, p.id, "X")
    assert servico.obter(ana, p.id).nome == "P"


# ---------- excluir ----------

def test_excluir_remove_projeto_e_todo_o_conteudo(servico, ana, conn):
    p = servico.criar(ana, "P")
    outro = servico.criar(ana, "Outro")
    _popular(conn, p.id)
    _popular(conn, outro.id)

    removido = servico.excluir(ana, p.id)

    assert (removido.backlogs, removido.historias, removido.epicos, removido.criterios) == (3, 2, 1, 3)
    with pytest.raises(ProjetoNaoEncontrado):
        servico.obter(ana, p.id)
    for tabela in ("backlog", "historia", "epico"):
        assert _um(conn, f"SELECT count(*) FROM {tabela} WHERE projeto_id = :p", p=p.id) == 0
    assert _um(conn, "SELECT count(*) FROM projeto_membro WHERE projeto_id = :p", p=p.id) == 0
    assert _um(conn, "SELECT count(*) FROM criterio_aceitacao") == 3  # só os do outro projeto
    assert _um(conn, "SELECT count(*) FROM epico_historia") == 1
    assert servico.obter(ana, outro.id).contagens.historias == 2  # o outro projeto segue intacto
    (aud,) = _auditoria(conn, "EXCLUIR")
    assert aud.entidade_id == p.id and aud.valor_posterior is None
    assert aud.valor_anterior["historias"] == 2 and aud.valor_anterior["nome"] == "P"


def test_excluir_projeto_vazio(servico, ana):
    p = servico.criar(ana, "Vazio")
    assert servico.excluir(ana, p.id).backlogs == 0
    assert servico.listar(ana) == []


def test_excluir_exige_ser_proprietario(servico, ana, beto, conn):
    p = servico.criar(ana, "P")
    with pytest.raises(ProjetoNaoEncontrado):
        servico.excluir(beto, p.id)
    conn.execute(text("INSERT INTO projeto_membro (projeto_id, usuario_id) VALUES (:p,:u)"), {"p": p.id, "u": beto})
    with pytest.raises(SemPermissao):
        servico.excluir(beto, p.id)
    assert servico.obter(ana, p.id).nome == "P"
    assert _auditoria(conn, "EXCLUIR") == []
