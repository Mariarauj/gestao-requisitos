"""Épicos (requisito 10)."""
import pytest

from sgr.services.auth_service import ErroDeValidacao
from sgr.services.epico_service import EpicoComHistorias, EpicoNaoEncontrado, NomeDeEpicoJaUsado
from sgr.services.projeto_service import ProjetoNaoEncontrado
from tests.fabricas import auditoria, cenario, criar_historia, novo_projeto  # noqa: F401


def test_criar_e_listar_epicos(cenario):
    e = cenario.epicos.criar(cenario.dono, cenario.projeto, "  Acesso  ", "  Login e conta ")
    assert (e.nome, e.descricao, e.historias, e.pontos) == ("Acesso", "Login e conta", 0, 0)
    cenario.epicos.criar(cenario.dono, cenario.projeto, "backlogs")
    assert [x.nome for x in cenario.epicos.listar(cenario.dono, cenario.projeto)] == ["Acesso", "backlogs"]
    primeira, segunda = auditoria(cenario.conn, "epico", "CRIAR")
    assert primeira.entidade_id == e.id and primeira.valor_posterior["nome"] == "Acesso"
    assert segunda.valor_posterior["nome"] == "backlogs"


def test_listagem_conta_historias_e_soma_pontos(cenario):
    e = cenario.epicos.criar(cenario.dono, cenario.projeto, "E")
    criar_historia(cenario, story_points=5, epicos_ids=[e.id])
    criar_historia(cenario, story_points=8, epicos_ids=[e.id])
    criar_historia(cenario, story_points=13)  # fora do épico
    (linha,) = cenario.epicos.listar(cenario.dono, cenario.projeto)
    assert (linha.historias, linha.pontos) == (2, 13)


@pytest.mark.parametrize("nome,descricao,chave", [
    ("", None, "nome"), ("   ", None, "nome"), (None, None, "nome"),
    ("x" * 121, None, "nome"), ("ok", "x" * 281, "descricao"),
])
def test_validacoes(cenario, nome, descricao, chave):
    with pytest.raises(ErroDeValidacao) as erro:
        cenario.epicos.criar(cenario.dono, cenario.projeto, nome, descricao)
    assert chave in erro.value.erros


def test_nome_unico_por_projeto_sem_diferenciar_maiusculas(cenario):
    cenario.epicos.criar(cenario.dono, cenario.projeto, "Acesso")
    with pytest.raises(NomeDeEpicoJaUsado):
        cenario.epicos.criar(cenario.dono, cenario.projeto, "ACESSO")
    p2, _ = novo_projeto(cenario.conn, cenario.dono, "P2")
    cenario.epicos.criar(cenario.dono, p2, "Acesso")  # outro projeto: permitido


def test_atualizar_reflete_nas_historias_ligadas(cenario):
    e = cenario.epicos.criar(cenario.dono, cenario.projeto, "Antigo")
    h = criar_historia(cenario, epicos_ids=[e.id])
    novo = cenario.epicos.atualizar(cenario.dono, e.id, "Novo nome", "desc")
    assert (novo.nome, novo.descricao, novo.historias) == ("Novo nome", "desc", 1)
    assert [x.nome for x in cenario.historias.obter(cenario.dono, h.id).epicos] == ["Novo nome"]
    (linha,) = auditoria(cenario.conn, "epico", "ALTERAR")
    assert linha.valor_anterior["nome"] == "Antigo" and linha.valor_posterior["nome"] == "Novo nome"


def test_atualizar_mantendo_o_proprio_nome_e_sem_mudanca(cenario):
    e = cenario.epicos.criar(cenario.dono, cenario.projeto, "Acesso")
    cenario.epicos.atualizar(cenario.dono, e.id, "acesso", None)  # só trocou maiúsculas: permitido
    cenario.epicos.atualizar(cenario.dono, e.id, "acesso", None)  # sem mudança: sem nova auditoria
    assert len(auditoria(cenario.conn, "epico", "ALTERAR")) == 1


def test_atualizar_para_nome_de_outro_epico_e_recusado(cenario):
    cenario.epicos.criar(cenario.dono, cenario.projeto, "A")
    b = cenario.epicos.criar(cenario.dono, cenario.projeto, "B")
    with pytest.raises(NomeDeEpicoJaUsado):
        cenario.epicos.atualizar(cenario.dono, b.id, "a")


def test_epico_com_historias_nao_pode_ser_excluido(cenario):
    e = cenario.epicos.criar(cenario.dono, cenario.projeto, "E")
    h = criar_historia(cenario, epicos_ids=[e.id])
    with pytest.raises(EpicoComHistorias) as erro:
        cenario.epicos.excluir(cenario.dono, e.id)
    assert erro.value.quantidade == 1 and "Remova os vínculos" in str(erro.value)
    assert cenario.epicos.obter(cenario.dono, e.id).epico.id == e.id
    cenario.historias.desvincular_epico(cenario.dono, h.id, e.id)
    cenario.epicos.excluir(cenario.dono, e.id)
    assert cenario.epicos.listar(cenario.dono, cenario.projeto) == []
    (linha,) = auditoria(cenario.conn, "epico", "EXCLUIR")
    assert linha.valor_anterior["nome"] == "E"


def test_obter_lista_historias_do_epico(cenario):
    e = cenario.epicos.criar(cenario.dono, cenario.projeto, "E")
    a = criar_historia(cenario, epicos_ids=[e.id], story_points=3)
    criar_historia(cenario)
    detalhe = cenario.epicos.obter(cenario.dono, e.id)
    assert [h.id for h in detalhe.historias] == [a.id]
    assert (detalhe.epico.historias, detalhe.epico.pontos) == (1, 3)


def test_isolamento_entre_usuarios(cenario):
    e = cenario.epicos.criar(cenario.dono, cenario.projeto, "E")
    with pytest.raises(ProjetoNaoEncontrado):
        cenario.epicos.listar(cenario.outro, cenario.projeto)
    with pytest.raises(ProjetoNaoEncontrado):
        cenario.epicos.criar(cenario.outro, cenario.projeto, "X")
    for operacao in (
        lambda: cenario.epicos.obter(cenario.outro, e.id),
        lambda: cenario.epicos.atualizar(cenario.outro, e.id, "Hack"),
        lambda: cenario.epicos.excluir(cenario.outro, e.id),
    ):
        with pytest.raises(EpicoNaoEncontrado):
            operacao()
    assert cenario.epicos.obter(cenario.dono, e.id).epico.nome == "E"
