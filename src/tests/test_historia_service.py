"""Histórias de usuário e vínculo com épicos (requisitos 7, 9 e 11)."""
import pytest
from sqlalchemy import text

from sgr.services.auth_service import ErroDeValidacao
from sgr.services.historia_service import HistoriaNaoEncontrada, ProductBacklogInexistente
from sgr.services.projeto_service import ProjetoNaoEncontrado
from tests.fabricas import auditoria, cenario, criar_historia, novo_projeto, um  # noqa: F401


# ---------- criar ----------

def test_cria_historia_no_product_backlog_com_frase_padrao(cenario):
    h = criar_historia(cenario)
    assert h.backlog_id == cenario.product and h.backlog_tipo == "PRODUCT"
    assert h.codigo == "SGR-1"
    assert h.frase == "Como um gerente de projetos, eu quero cadastrar projetos, para organizar o trabalho"
    assert h.moscow == "S" and h.story_points is None and h.epicos == ()
    assert [x.id for x in cenario.historias.listar(cenario.dono, cenario.projeto)] == [h.id]


def test_criacao_com_story_points_moscow_e_epicos(cenario):
    e1 = cenario.epicos.criar(cenario.dono, cenario.projeto, "Acesso")
    e2 = cenario.epicos.criar(cenario.dono, cenario.projeto, "Projetos")
    h = criar_historia(cenario, story_points=8, moscow="m", epicos_ids=[e2.id, e1.id])
    assert (h.story_points, h.moscow) == (8, "M")
    assert [e.nome for e in h.epicos] == ["Acesso", "Projetos"]


def test_nao_cria_sem_product_backlog_e_explica(cenario):
    pid, _ = novo_projeto(cenario.conn, cenario.dono, "Sem backlog", com_product=False)
    with pytest.raises(ProductBacklogInexistente) as erro:
        cenario.historias.criar(cenario.dono, pid, "a", "b", "c")
    assert "product backlog" in str(erro.value)


def test_codigos_sequenciais_reiniciam_por_projeto_e_nao_repetem_ao_apagar_no_meio(cenario):
    h1, h2, h3 = (criar_historia(cenario) for _ in range(3))
    assert [h1.codigo, h2.codigo, h3.codigo] == ["SGR-1", "SGR-2", "SGR-3"]
    cenario.historias.excluir(cenario.dono, h2.id)
    assert criar_historia(cenario).codigo == "SGR-4"
    outro_projeto, _ = novo_projeto(cenario.conn, cenario.dono, "Outro")  # já vem com product backlog
    assert cenario.historias.criar(cenario.dono, outro_projeto, "a", "b", "c").codigo == "SGR-1"


@pytest.mark.parametrize("campos,chaves", [
    ({"papel": " "}, {"papel"}),
    ({"acao": ""}, {"acao"}),
    ({"beneficio": None}, {"beneficio"}),
    ({"papel": "", "acao": "", "beneficio": ""}, {"papel", "acao", "beneficio"}),
    ({"papel": "x" * 121}, {"papel"}),
    ({"acao": "x" * 201}, {"acao"}),
    ({"beneficio": "x" * 201}, {"beneficio"}),
    ({"story_points": 4}, {"story_points"}),
    ({"story_points": True}, {"story_points"}),
    ({"moscow": "X"}, {"moscow"}),
])
def test_validacoes_indicam_o_que_falta(cenario, campos, chaves):
    with pytest.raises(ErroDeValidacao) as erro:
        criar_historia(cenario, **campos)
    assert set(erro.value.erros) == chaves
    assert cenario.historias.listar(cenario.dono, cenario.projeto) == []


def test_erro_de_story_points_lista_os_valores_aceitos(cenario):
    with pytest.raises(ErroDeValidacao) as erro:
        criar_historia(cenario, story_points=7)
    assert "0, 1, 2, 3, 5, 8, 13, 21, 34, 55" in erro.value.erros["story_points"]


def test_epico_de_outro_projeto_e_recusado_na_criacao(cenario):
    p2, _ = novo_projeto(cenario.conn, cenario.dono, "P2")
    estranho = cenario.epicos.criar(cenario.dono, p2, "Estranho")
    with pytest.raises(ErroDeValidacao) as erro:
        criar_historia(cenario, epicos_ids=[estranho.id])
    assert "epicos" in erro.value.erros
    assert cenario.historias.listar(cenario.dono, cenario.projeto) == []


def test_criacao_e_auditada(cenario):
    h = criar_historia(cenario, story_points=3)
    (linha,) = auditoria(cenario.conn, "historia", "CRIAR")
    assert linha.entidade_id == h.id and linha.valor_posterior["codigo"] == "SGR-1"
    assert linha.valor_posterior["story_points"] == 3


# ---------- ler ----------

def test_listar_com_filtros(cenario):
    e = cenario.epicos.criar(cenario.dono, cenario.projeto, "E")
    a = criar_historia(cenario, moscow="M", epicos_ids=[e.id])
    b = criar_historia(cenario, moscow="W")
    sprint = um(cenario.conn, "INSERT INTO backlog (projeto_id,tipo,nome,data_inicio,data_fim,estado) VALUES (:p,'SPRINT','S1','2026-11-16','2026-11-30','PLANEJADO') RETURNING id", p=cenario.projeto)
    cenario.conn.execute(text("UPDATE historia SET backlog_id=:s WHERE id=:h"), {"s": sprint, "h": b.id})
    ids = lambda **f: [h.id for h in cenario.historias.listar(cenario.dono, cenario.projeto, **f)]
    assert ids() == [a.id, b.id]
    assert ids(epico_id=e.id) == [a.id]
    assert ids(moscow="w") == [b.id]
    assert ids(backlog_id=sprint) == [b.id]
    assert ids(backlog_id=cenario.product) == [a.id]
    with pytest.raises(ErroDeValidacao):
        ids(moscow="Z")


def test_obter_traz_criterios_em_ordem(cenario):
    h = criar_historia(cenario)
    cenario.criterios.criar(cenario.dono, h.id, "c1", "a1", "r1")
    cenario.criterios.criar(cenario.dono, h.id, "c2", "a2", "r2")
    completo = cenario.historias.obter(cenario.dono, h.id)
    assert [c.ordem for c in completo.criterios] == [1, 2]
    assert completo.criterios_total == 2


def test_isolamento_entre_usuarios(cenario):
    h = criar_historia(cenario)
    with pytest.raises(ProjetoNaoEncontrado):
        cenario.historias.listar(cenario.outro, cenario.projeto)
    with pytest.raises(ProjetoNaoEncontrado):
        cenario.historias.criar(cenario.outro, cenario.projeto, "a", "b", "c")
    for operacao in (
        lambda: cenario.historias.obter(cenario.outro, h.id),
        lambda: cenario.historias.atualizar(cenario.outro, h.id, "a", "b", "c"),
        lambda: cenario.historias.excluir(cenario.outro, h.id),
        lambda: cenario.historias.definir_epicos(cenario.outro, h.id, []),
    ):
        with pytest.raises(HistoriaNaoEncontrada):
            operacao()
    assert cenario.historias.obter(cenario.dono, h.id).papel == h.papel  # nada foi alterado


def test_membro_do_projeto_tambem_gerencia_historias(cenario):
    cenario.conn.execute(text("INSERT INTO projeto_membro (projeto_id, usuario_id) VALUES (:p,:u)"), {"p": cenario.projeto, "u": cenario.outro})
    h = cenario.historias.criar(cenario.outro, cenario.projeto, "a", "b", "c")
    assert cenario.historias.obter(cenario.dono, h.id).id == h.id


# ---------- atualizar ----------

def test_atualizar_mantem_codigo_e_backlog_e_audita(cenario):
    h = criar_historia(cenario, story_points=5, moscow="M")
    novo = cenario.historias.atualizar(cenario.dono, h.id, "analista", "filtrar", "achar rápido", story_points=8, moscow="c")
    assert (novo.codigo, novo.backlog_id) == (h.codigo, h.backlog_id)
    assert (novo.papel, novo.story_points, novo.moscow) == ("analista", 8, "C")
    (linha,) = auditoria(cenario.conn, "historia", "ALTERAR")
    assert linha.valor_anterior["papel"] == "gerente de projetos" and linha.valor_posterior["papel"] == "analista"


def test_atualizar_sem_moscow_mantem_e_story_points_none_limpa(cenario):
    h = criar_historia(cenario, story_points=5, moscow="W")
    novo = cenario.historias.atualizar(cenario.dono, h.id, h.papel, h.acao, h.beneficio)
    assert (novo.moscow, novo.story_points) == ("W", None)


def test_atualizar_sem_mudanca_nao_gera_auditoria(cenario):
    h = criar_historia(cenario, story_points=2)
    cenario.historias.atualizar(cenario.dono, h.id, h.papel, h.acao, h.beneficio, story_points=2)
    assert auditoria(cenario.conn, "historia", "ALTERAR") == []


def test_atualizar_valida(cenario):
    h = criar_historia(cenario)
    with pytest.raises(ErroDeValidacao) as erro:
        cenario.historias.atualizar(cenario.dono, h.id, "", h.acao, h.beneficio, story_points=9)
    assert set(erro.value.erros) == {"papel", "story_points"}


# ---------- vínculo com épicos ----------

def test_vincular_desvincular_e_idempotencia(cenario):
    e = cenario.epicos.criar(cenario.dono, cenario.projeto, "E")
    h = criar_historia(cenario)
    assert [x.id for x in cenario.historias.vincular_epico(cenario.dono, h.id, e.id).epicos] == [e.id]
    cenario.historias.vincular_epico(cenario.dono, h.id, e.id)  # repetir não duplica nem falha
    assert len(auditoria(cenario.conn, "historia", "ALTERAR")) == 1
    assert [s.id for s in cenario.epicos.obter(cenario.dono, e.id).historias] == [h.id]
    assert cenario.historias.desvincular_epico(cenario.dono, h.id, e.id).epicos == ()
    assert cenario.epicos.obter(cenario.dono, e.id).historias == ()
    assert cenario.historias.obter(cenario.dono, h.id).id == h.id  # a história não foi apagada


def test_historia_com_varios_epicos_e_definir_epicos(cenario):
    e1, e2, e3 = (cenario.epicos.criar(cenario.dono, cenario.projeto, n) for n in ("A", "B", "C"))
    h = criar_historia(cenario, epicos_ids=[e1.id, e2.id])
    novo = cenario.historias.definir_epicos(cenario.dono, h.id, [e2.id, e3.id])
    assert sorted(e.nome for e in novo.epicos) == ["B", "C"]
    assert cenario.historias.definir_epicos(cenario.dono, h.id, []).epicos == ()


def test_vinculo_com_epico_de_outro_projeto_e_recusado(cenario):
    p2, _ = novo_projeto(cenario.conn, cenario.dono, "P2")
    estranho = cenario.epicos.criar(cenario.dono, p2, "Estranho")
    h = criar_historia(cenario)
    with pytest.raises(ErroDeValidacao):
        cenario.historias.vincular_epico(cenario.dono, h.id, estranho.id)
    with pytest.raises(ErroDeValidacao):
        cenario.historias.vincular_epico(cenario.dono, h.id, 999999)


# ---------- excluir ----------

def test_excluir_remove_criterios_e_vinculos_mas_preserva_epico(cenario):
    e = cenario.epicos.criar(cenario.dono, cenario.projeto, "E")
    h = criar_historia(cenario, epicos_ids=[e.id])
    cenario.criterios.criar(cenario.dono, h.id, "c", "a", "r")
    cenario.criterios.criar(cenario.dono, h.id, "c2", "a2", "r2")
    inventario = cenario.historias.inventario(cenario.dono, h.id)
    assert (inventario.criterios, inventario.epicos) == (2, 1)
    feito = cenario.historias.excluir(cenario.dono, h.id)
    assert (feito.criterios, feito.epicos) == (2, 1)
    assert cenario.historias.listar(cenario.dono, cenario.projeto) == []
    assert um(cenario.conn, "SELECT count(*) FROM criterio_aceitacao") == 0
    assert um(cenario.conn, "SELECT count(*) FROM epico_historia") == 0
    assert cenario.epicos.obter(cenario.dono, e.id).epico.historias == 0
    (linha,) = auditoria(cenario.conn, "historia", "EXCLUIR")
    assert linha.valor_anterior["criterios"] == 2 and linha.valor_anterior["epicos"] == [e.id]
    with pytest.raises(HistoriaNaoEncontrada):
        cenario.historias.obter(cenario.dono, h.id)
