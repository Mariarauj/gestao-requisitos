"""Texto que o banco não aceita (byte NUL e caractere substituto isolado).

O PostgreSQL recusa NUL (0x00) em colunas de texto e o UTF-8 não representa um substituto
isolado como "\\ud800". Sem tratamento, qualquer campo de texto derrubava o serviço com
DataError/UnicodeEncodeError. Aqui cada ponto de entrada de texto é exercitado com os dois
valores: o esperado é um erro de validação do campo (ou "credenciais inválidas" no login, ou
lista vazia na busca), nunca uma exceção de banco, e nada gravado.
"""
from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from sgr.services.auth_service import AuthService, CredenciaisInvalidas, ErroDeValidacao
from sgr.services.backlog_service import BacklogService
from sgr.services.criterio_service import CriterioService
from sgr.services.epico_service import EpicoService
from sgr.services.historia_service import HistoriaService
from sgr.services.priorizacao_service import PriorizacaoService
from sgr.services.projeto_service import ProjetoService
from tests.fabricas import novo_projeto, novo_usuario, um

RUINS = {"nul": "ab\x00cd", "substituto": "ab\ud800cd"}


@pytest.fixture(params=RUINS.values(), ids=RUINS.keys())
def ruim(request):
    return request.param


@pytest.fixture()
def c(conn):
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
    projeto, product = novo_projeto(conn, dono)
    sprint = um(conn, "INSERT INTO backlog (projeto_id, tipo, nome, data_inicio, data_fim, estado) "
                      "VALUES (:p,'SPRINT','S1','2026-01-01','2026-01-15','PLANEJADO') RETURNING id", p=projeto)
    s = SimpleNamespace(
        conn=conn, dono=dono, projeto=projeto, product=product, sprint=sprint,
        auth=AuthService(sessao, rounds=4), projetos=ProjetoService(sessao), backlogs=BacklogService(sessao),
        epicos=EpicoService(sessao), historias=HistoriaService(sessao), criterios=CriterioService(sessao),
        priorizacao=PriorizacaoService(sessao),
    )
    s.historia = s.historias.criar(dono, projeto, "gerente", "cadastrar", "organizar").id
    s.epico = s.epicos.criar(dono, projeto, "Catálogo").id
    s.criterio = s.criterios.criar(dono, s.historia, "estou logado", "clico", "vejo").id
    return s


def _contagem(conn, tabela):
    return um(conn, f"SELECT count(*) FROM {tabela}")


# ---------- campos de texto: erro de validação no próprio campo ----------

def _casos_validacao():
    ok = {"descricao": "d"}
    return [
        # (rótulo, campo esperado no erro, função(c, v))
        ("auth.cadastrar nome", "nome", lambda c, v: c.auth.cadastrar(v, "a@x.com", "senha-segura-123", "senha-segura-123")),
        ("auth.cadastrar email", "email", lambda c, v: c.auth.cadastrar("Ana", v, "senha-segura-123", "senha-segura-123")),
        ("auth.cadastrar senha", "senha", lambda c, v: c.auth.cadastrar("Ana", "a@x.com", v + "xxxxxxxx", v + "xxxxxxxx")),
        ("projeto.criar nome", "nome", lambda c, v: c.projetos.criar(c.dono, v)),
        ("projeto.criar descricao", "descricao", lambda c, v: c.projetos.criar(c.dono, "P", v)),
        ("projeto.atualizar nome", "nome", lambda c, v: c.projetos.atualizar(c.dono, c.projeto, v)),
        ("projeto.atualizar descricao", "descricao", lambda c, v: c.projetos.atualizar(c.dono, c.projeto, "P", v)),
        ("backlog.criar_sprint nome", "nome", lambda c, v: c.backlogs.criar_sprint(c.dono, c.projeto, v, date(2026, 2, 1), date(2026, 2, 14))),
        ("backlog.criar_sprint meta", "descricao", lambda c, v: c.backlogs.criar_sprint(c.dono, c.projeto, "S2", date(2026, 2, 1), date(2026, 2, 14), v)),
        ("backlog.atualizar product nome", "nome", lambda c, v: c.backlogs.atualizar(c.dono, c.product, v)),
        ("backlog.atualizar sprint meta", "descricao", lambda c, v: c.backlogs.atualizar(c.dono, c.sprint, "S1", v, date(2026, 1, 1), date(2026, 1, 15))),
        ("epico.criar nome", "nome", lambda c, v: c.epicos.criar(c.dono, c.projeto, v)),
        ("epico.criar descricao", "descricao", lambda c, v: c.epicos.criar(c.dono, c.projeto, "Novo", v)),
        ("epico.atualizar nome", "nome", lambda c, v: c.epicos.atualizar(c.dono, c.epico, v)),
        ("historia.criar papel", "papel", lambda c, v: c.historias.criar(c.dono, c.projeto, v, "agir", "ganhar")),
        ("historia.criar acao", "acao", lambda c, v: c.historias.criar(c.dono, c.projeto, "gerente", v, "ganhar")),
        ("historia.criar beneficio", "beneficio", lambda c, v: c.historias.criar(c.dono, c.projeto, "gerente", "agir", v)),
        ("historia.criar moscow", "moscow", lambda c, v: c.historias.criar(c.dono, c.projeto, "g", "a", "b", moscow=v)),
        ("historia.atualizar acao", "acao", lambda c, v: c.historias.atualizar(c.dono, c.historia, "gerente", v, "ganhar")),
        ("historia.listar moscow", "moscow", lambda c, v: c.historias.listar(c.dono, c.projeto, moscow=v)),
        ("historia.listar ordenar_por", "ordenar_por", lambda c, v: c.historias.listar(c.dono, c.projeto, ordenar_por=v)),
        ("historia.listar ordem", "ordem", lambda c, v: c.historias.listar(c.dono, c.projeto, ordenar_por="rice", ordem=v)),
        ("historia.listar rice_min (texto)", "rice_min", lambda c, v: c.historias.listar(c.dono, c.projeto, rice_min=v)),
        ("historia.listar rice_max (texto)", "rice_max", lambda c, v: c.historias.listar(c.dono, c.projeto, rice_max=v)),
        ("criterio.criar contexto", "contexto", lambda c, v: c.criterios.criar(c.dono, c.historia, v, "a", "r")),
        ("criterio.criar acao", "acao", lambda c, v: c.criterios.criar(c.dono, c.historia, "c", v, "r")),
        ("criterio.criar resultado", "resultado", lambda c, v: c.criterios.criar(c.dono, c.historia, "c", "a", v)),
        ("criterio.atualizar resultado", "resultado", lambda c, v: c.criterios.atualizar(c.dono, c.criterio, "c", "a", v)),
        ("priorizacao.definir_moscow", None, lambda c, v: c.priorizacao.definir_moscow(c.dono, c.historia, v)),
    ]


CASOS = _casos_validacao()


@pytest.mark.parametrize("rotulo, campo, chamar", CASOS, ids=[x[0] for x in CASOS])
def test_texto_invalido_vira_erro_de_validacao_no_campo(c, ruim, rotulo, campo, chamar):
    antes = {t: _contagem(c.conn, t) for t in ("usuario", "projeto", "backlog", "epico", "historia", "criterio_aceitacao")}
    with pytest.raises(ErroDeValidacao) as e:
        chamar(c, ruim)
    if campo is not None:
        assert campo in e.value.erros
    depois = {t: _contagem(c.conn, t) for t in antes}
    assert depois == antes  # nada foi gravado


# ---------- login e busca: sem campo para mostrar o erro ----------

def test_login_com_texto_invalido_e_credencial_invalida(c, ruim):
    c.auth.cadastrar("Ana", "ana@x.com", "senha-segura-123", "senha-segura-123")
    with pytest.raises(CredenciaisInvalidas):
        c.auth.autenticar(ruim + "@x.com", "senha-segura-123")
    with pytest.raises(CredenciaisInvalidas):
        c.auth.autenticar("ana@x.com", ruim)


def test_busca_de_projeto_com_texto_invalido_nao_encontra_nada(c, ruim):
    assert c.projetos.listar(c.dono, busca=ruim) == []


def test_texto_valido_com_acentos_e_emoji_continua_aceito(c):
    p = c.projetos.criar(c.dono, "Gestão de requisitos 🚀", "Ação, coração, café")
    assert p.nome == "Gestão de requisitos 🚀"


# ---------- guarda: parâmetro de texto novo precisa ser coberto aqui ----------

# Todo parâmetro de texto dos serviços públicos e onde ele é exercitado acima. "confirmacao" só
# é comparado com a senha (já validada), nunca chega ao banco nem é codificado.
PARAMETROS_DE_TEXTO = {
    "AuthService.autenticar": {"email", "senha"},
    "AuthService.cadastrar": {"nome", "email", "senha", "confirmacao"},
    "BacklogService.atualizar": {"nome", "descricao"},
    "BacklogService.criar_product": {"nome", "descricao"},
    "BacklogService.criar_sprint": {"nome", "meta"},
    "CriterioService.atualizar": {"contexto", "acao", "resultado"},
    "CriterioService.criar": {"contexto", "acao", "resultado"},
    "EpicoService.atualizar": {"nome", "descricao"},
    "EpicoService.criar": {"nome", "descricao"},
    "HistoriaService.atualizar": {"papel", "acao", "beneficio", "moscow"},
    "HistoriaService.criar": {"papel", "acao", "beneficio", "moscow"},
    # moscow, ordenar_por e ordem só aceitam valores de uma lista fixa: texto com NUL/substituto
    # nunca está nela e é recusado antes de qualquer consulta (casos "historia.listar ..." acima).
    "HistoriaService.listar": {"moscow", "ordenar_por", "ordem"},
    "PriorizacaoService.definir_moscow": {"moscow"},
    "ProjetoService.atualizar": {"nome", "descricao"},
    "ProjetoService.criar": {"nome", "descricao"},
    "ProjetoService.listar": {"busca"},
}


def test_todo_parametro_de_texto_dos_servicos_esta_coberto():
    import inspect

    encontrados: dict[str, set[str]] = {}
    for cls in (AuthService, BacklogService, CriterioService, EpicoService, HistoriaService,
                PriorizacaoService, ProjetoService):
        for nome, funcao in inspect.getmembers(cls, inspect.isfunction):
            if nome.startswith("_"):
                continue
            textos = {p.name for p in inspect.signature(funcao).parameters.values() if "str" in str(p.annotation)}
            if textos:
                encontrados[f"{cls.__name__}.{nome}"] = textos
    assert encontrados == PARAMETROS_DE_TEXTO, (
        "Há parâmetro de texto novo (ou removido) nos serviços. Valide-o com caractere_invalido(), "
        "acrescente um caso nesta suíte e atualize PARAMETROS_DE_TEXTO."
    )
