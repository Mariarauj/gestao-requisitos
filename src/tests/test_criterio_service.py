"""Critérios de aceitação (requisitos 12 e 13)."""
import pytest

from sgr.services.auth_service import ErroDeValidacao
from sgr.services.criterio_service import CriterioNaoEncontrado
from sgr.services.historia_service import HistoriaNaoEncontrada
from tests.fabricas import auditoria, cenario, criar_historia  # noqa: F401


def _criar(c, h, n=1):
    return c.criterios.criar(c.dono, h.id, f"contexto {n}", f"ação {n}", f"resultado {n}")


def test_cria_criterio_no_formato_padrao_dentro_da_historia(cenario):
    h = criar_historia(cenario)
    c = cenario.criterios.criar(cenario.dono, h.id, "estou logado", "crio um projeto", "ele aparece na lista")
    assert c.frase == "Dado estou logado, quando crio um projeto, então ele aparece na lista"
    assert (c.historia_id, c.ordem) == (h.id, 1)
    assert [x.id for x in cenario.criterios.listar(cenario.dono, h.id)] == [c.id]
    (linha,) = auditoria(cenario.conn, "criterio_aceitacao", "CRIAR")
    assert linha.entidade_id == c.id and linha.valor_posterior["historia_id"] == h.id


def test_novos_criterios_entram_no_fim(cenario):
    h = criar_historia(cenario)
    assert [_criar(cenario, h, n).ordem for n in (1, 2, 3)] == [1, 2, 3]


@pytest.mark.parametrize("campos,chaves", [
    (("", "a", "r"), {"contexto"}),
    (("c", "  ", "r"), {"acao"}),
    (("c", "a", None), {"resultado"}),
    (("", "", ""), {"contexto", "acao", "resultado"}),
])
def test_campo_vazio_indica_o_que_falta(cenario, campos, chaves):
    h = criar_historia(cenario)
    with pytest.raises(ErroDeValidacao) as erro:
        cenario.criterios.criar(cenario.dono, h.id, *campos)
    assert set(erro.value.erros) == chaves
    assert cenario.criterios.listar(cenario.dono, h.id) == []


def test_editar_salva_e_audita(cenario):
    h = criar_historia(cenario)
    c = _criar(cenario, h)
    novo = cenario.criterios.atualizar(cenario.dono, c.id, "novo contexto", "nova ação", "novo resultado")
    assert novo.ordem == c.ordem and novo.contexto == "novo contexto"
    assert cenario.criterios.listar(cenario.dono, h.id)[0].resultado == "novo resultado"
    (linha,) = auditoria(cenario.conn, "criterio_aceitacao", "ALTERAR")
    assert linha.valor_anterior["contexto"] == "contexto 1" and linha.valor_posterior["contexto"] == "novo contexto"
    with pytest.raises(ErroDeValidacao):
        cenario.criterios.atualizar(cenario.dono, c.id, "", "a", "r")


def test_apagar_mantem_os_demais_e_novo_vai_para_o_fim(cenario):
    h = criar_historia(cenario)
    c1, c2, c3 = (_criar(cenario, h, n) for n in (1, 2, 3))
    cenario.criterios.excluir(cenario.dono, c2.id)
    assert [x.id for x in cenario.criterios.listar(cenario.dono, h.id)] == [c1.id, c3.id]
    assert _criar(cenario, h, 4).ordem == 4  # nunca colide com a ordem existente
    (linha,) = auditoria(cenario.conn, "criterio_aceitacao", "EXCLUIR")
    assert linha.entidade_id == c2.id
    with pytest.raises(CriterioNaoEncontrado):
        cenario.criterios.excluir(cenario.dono, c2.id)


def test_criterios_nao_se_misturam_entre_historias(cenario):
    h1, h2 = criar_historia(cenario), criar_historia(cenario)
    _criar(cenario, h1)
    assert cenario.criterios.listar(cenario.dono, h2.id) == []
    assert _criar(cenario, h2).ordem == 1


def test_isolamento_entre_usuarios(cenario):
    h = criar_historia(cenario)
    c = _criar(cenario, h)
    with pytest.raises(HistoriaNaoEncontrada):
        cenario.criterios.listar(cenario.outro, h.id)
    with pytest.raises(HistoriaNaoEncontrada):
        cenario.criterios.criar(cenario.outro, h.id, "c", "a", "r")
    for operacao in (
        lambda: cenario.criterios.atualizar(cenario.outro, c.id, "x", "y", "z"),
        lambda: cenario.criterios.excluir(cenario.outro, c.id),
    ):
        with pytest.raises(CriterioNaoEncontrado):
            operacao()
    assert cenario.criterios.listar(cenario.dono, h.id)[0].contexto == "contexto 1"
