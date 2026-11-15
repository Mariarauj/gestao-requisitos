"""Criação simultânea contra o PostgreSQL real, com várias threads e conexões de verdade.

Os testes unitários rodam numa única transação e nunca veem uma corrida. Aqui cada cenário
abre N sessões independentes (commit real) e faz todas passarem pela checagem "já existe?"
antes de qualquer uma gravar, que é exatamente a janela em que o banco é a última defesa.
A barreira que força a janela tolera timeout: se o código serializar as threads com uma trava,
quem espera segue adiante depois de meio segundo, e o teste continua valendo.

Invariantes verificadas: exatamente um vencedor, os demais recebem o erro de domínio esperado
(nunca IntegrityError/DataError), o banco guarda uma só linha e a auditoria tem um só registro.
"""
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from itertools import count

import pytest
from sqlalchemy import text

from sgr.db import session as db_session
from sgr.repositories import (
    backlog_repository,
    criterio_repository,
    epico_repository,
    historia_repository,
    projeto_repository,
    usuario_repository,
)
from sgr.services.auth_service import AuthService, EmailJaCadastrado
from sgr.services.backlog_service import BacklogService, ProductBacklogJaExiste
from sgr.services.criterio_service import CriterioService
from sgr.services.epico_service import EpicoService, NomeDeEpicoJaUsado
from sgr.services.historia_service import HistoriaService
from sgr.services.projeto_service import NomeJaUsado, ProjetoService

N = 8
SENHA = "senha-segura-123"


@pytest.fixture()
def real(engine, test_url, monkeypatch):
    """Serviços ligados ao banco de testes com sessões reais (commit de verdade)."""
    monkeypatch.setenv("DATABASE_URL", test_url)
    db_session.get_engine.cache_clear()
    db_session._session_factory.cache_clear()

    def limpar():
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE usuario RESTART IDENTITY CASCADE"))
            conn.execute(text("TRUNCATE registro_auditoria"))

    limpar()
    from types import SimpleNamespace

    s = SimpleNamespace(
        engine=engine,
        auth=AuthService(rounds=4),
        projetos=ProjetoService(),
        backlogs=BacklogService(),
        epicos=EpicoService(),
        historias=HistoriaService(),
        criterios=CriterioService(),
    )
    s.dono = s.auth.cadastrar("Dono", "dono@x.com", SENHA, SENHA)
    yield s
    db_session.get_engine().dispose()
    db_session.get_engine.cache_clear()
    db_session._session_factory.cache_clear()
    limpar()


# ---------- ferramentas ----------

def em_paralelo(tarefas, timeout=60):
    """Roda as tarefas ao mesmo tempo (largada sincronizada). Devolve [("ok", valor) | ("erro", exc)]."""
    largada = threading.Barrier(len(tarefas), timeout=15)

    def rodar(tarefa):
        largada.wait()
        try:
            return ("ok", tarefa())
        except BaseException as erro:  # noqa: BLE001 - o teste examina qualquer tipo de falha
            return ("erro", erro)

    with ThreadPoolExecutor(max_workers=len(tarefas)) as pool:
        futuros = [pool.submit(rodar, t) for t in tarefas]
        return [f.result(timeout=timeout) for f in futuros]


def forcar_janela(monkeypatch, modulo, nome, n=N, depois=True):
    """Faz as n primeiras chamadas de `modulo.nome` se esperarem entre si.

    depois=True: cada thread executa a função e só então espera (todas já "viram" que não existe
    nada e, juntas, vão gravar). depois=False: esperam antes de entrar (largada na trava).
    O timeout curto mantém o teste válido quando uma trava impede o encontro das threads.
    """
    original = getattr(modulo, nome)
    barreira = threading.Barrier(n, timeout=0.5)
    vez = count()
    trava = threading.Lock()

    def esperar():
        with trava:
            minha = next(vez)
        if minha < n:
            try:
                barreira.wait()
            except threading.BrokenBarrierError:
                pass

    def envolvida(*args, **kwargs):
        if not depois:
            esperar()
        resultado = original(*args, **kwargs)
        if depois:
            esperar()
        return resultado

    monkeypatch.setattr(modulo, nome, envolvida)


def separar(resultados, esperado):
    """Confere que há 1 vencedor e que todo perdedor recebeu o erro de domínio `esperado`."""
    vencedores = [v for t, v in resultados if t == "ok"]
    perdedores = [v for t, v in resultados if t == "erro"]
    inesperados = [repr(e) for e in perdedores if not isinstance(e, esperado)]
    assert inesperados == [], f"exceção que não é de domínio: {inesperados}"
    assert len(vencedores) == 1, f"{len(vencedores)} vencedores, esperado 1"
    assert len(perdedores) == len(resultados) - 1
    return vencedores[0]


def um(real, sql, **p):
    with real.engine.connect() as c:
        return c.execute(text(sql), p).scalar_one()


def auditorias(real, entidade, operacao):
    return um(real, "SELECT count(*) FROM registro_auditoria WHERE entidade=:e AND operacao=:o", e=entidade, o=operacao)


# ---------- unicidade: o banco é a última defesa ----------

def test_cadastro_simultaneo_do_mesmo_email_cria_so_um_usuario(real, monkeypatch):
    forcar_janela(monkeypatch, usuario_repository, "buscar_por_email")
    res = em_paralelo([lambda: real.auth.cadastrar("Ana", "ana@x.com", SENHA, SENHA) for _ in range(N)])
    separar(res, EmailJaCadastrado)
    assert um(real, "SELECT count(*) FROM usuario WHERE email='ana@x.com'") == 1


def test_criacao_simultanea_de_projeto_com_o_mesmo_nome(real, monkeypatch):
    forcar_janela(monkeypatch, projeto_repository, "existe_nome")
    res = em_paralelo([lambda: real.projetos.criar(real.dono.id, "Portal") for _ in range(N)])
    separar(res, NomeJaUsado)
    assert um(real, "SELECT count(*) FROM projeto WHERE nome='Portal'") == 1
    assert auditorias(real, "projeto", "CRIAR") == 1  # perdedores não deixam rastro


def test_renomeacao_simultanea_de_projetos_para_o_mesmo_nome(real, monkeypatch):
    projetos = [real.projetos.criar(real.dono.id, f"P{i}") for i in range(N)]
    forcar_janela(monkeypatch, projeto_repository, "existe_nome")
    res = em_paralelo([lambda p=p: real.projetos.atualizar(real.dono.id, p.id, "Alvo") for p in projetos])
    separar(res, NomeJaUsado)
    assert um(real, "SELECT count(*) FROM projeto WHERE nome='Alvo'") == 1
    assert auditorias(real, "projeto", "ALTERAR") == 1


def test_criacao_simultanea_de_epico_com_o_mesmo_nome(real, monkeypatch):
    projeto = real.projetos.criar(real.dono.id, "P")
    forcar_janela(monkeypatch, epico_repository, "existe_nome")
    res = em_paralelo([lambda: real.epicos.criar(real.dono.id, projeto.id, "Catálogo") for _ in range(N)])
    separar(res, NomeDeEpicoJaUsado)
    assert um(real, "SELECT count(*) FROM epico WHERE nome='Catálogo'") == 1
    assert auditorias(real, "epico", "CRIAR") == 1


def test_renomeacao_simultanea_de_epicos_para_o_mesmo_nome(real, monkeypatch):
    projeto = real.projetos.criar(real.dono.id, "P")
    epicos = [real.epicos.criar(real.dono.id, projeto.id, f"E{i}") for i in range(N)]
    forcar_janela(monkeypatch, epico_repository, "existe_nome")
    res = em_paralelo([lambda e=e: real.epicos.atualizar(real.dono.id, e.id, "Alvo") for e in epicos])
    separar(res, NomeDeEpicoJaUsado)
    assert um(real, "SELECT count(*) FROM epico WHERE nome='Alvo'") == 1


def test_criacao_simultanea_do_product_backlog_cria_so_um(real, monkeypatch):
    projeto = real.projetos.criar(real.dono.id, "P")
    forcar_janela(monkeypatch, backlog_repository, "product_do_projeto")
    res = em_paralelo([lambda: real.backlogs.criar_product(real.dono.id, projeto.id, "Product Backlog") for _ in range(N)])
    separar(res, ProductBacklogJaExiste)
    assert um(real, "SELECT count(*) FROM backlog WHERE tipo='PRODUCT'") == 1
    assert auditorias(real, "backlog", "CRIAR") == 1


# ---------- unicidade sem diferenciar maiúsculas ----------
# O banco só impede nomes idênticos; "Portal" e "portal" só são barrados pela checagem do
# serviço, que numa corrida enxerga o mesmo "nada" nos dois lados. Por isso precisa de trava.

VARIANTES = ["Portal", "portal", "PORTAL", "pOrTaL", "pORTAL", "PoRtAl", "portAL", "POrtal"]


def test_criacao_simultanea_de_projetos_que_diferem_so_em_maiusculas(real, monkeypatch):
    forcar_janela(monkeypatch, projeto_repository, "existe_nome")
    res = em_paralelo([lambda n=n: real.projetos.criar(real.dono.id, n) for n in VARIANTES])
    separar(res, NomeJaUsado)
    assert um(real, "SELECT count(*) FROM projeto WHERE lower(nome)='portal'") == 1


def test_renomeacao_simultanea_de_projetos_para_nomes_que_diferem_so_em_maiusculas(real, monkeypatch):
    projetos = [real.projetos.criar(real.dono.id, f"P{i}") for i in range(N)]
    forcar_janela(monkeypatch, projeto_repository, "existe_nome")
    res = em_paralelo([lambda p=p, n=n: real.projetos.atualizar(real.dono.id, p.id, n) for p, n in zip(projetos, VARIANTES)])
    separar(res, NomeJaUsado)
    assert um(real, "SELECT count(*) FROM projeto WHERE lower(nome)='portal'") == 1


def test_criacao_simultanea_de_epicos_que_diferem_so_em_maiusculas(real, monkeypatch):
    projeto = real.projetos.criar(real.dono.id, "P")
    forcar_janela(monkeypatch, epico_repository, "existe_nome")
    res = em_paralelo([lambda n=n: real.epicos.criar(real.dono.id, projeto.id, n) for n in VARIANTES])
    separar(res, NomeDeEpicoJaUsado)
    assert um(real, "SELECT count(*) FROM epico WHERE lower(nome)='portal'") == 1


def test_renomeacao_simultanea_de_epicos_para_nomes_que_diferem_so_em_maiusculas(real, monkeypatch):
    projeto = real.projetos.criar(real.dono.id, "P")
    epicos = [real.epicos.criar(real.dono.id, projeto.id, f"E{i}") for i in range(N)]
    forcar_janela(monkeypatch, epico_repository, "existe_nome")
    res = em_paralelo([lambda e=e, n=n: real.epicos.atualizar(real.dono.id, e.id, n) for e, n in zip(epicos, VARIANTES)])
    separar(res, NomeDeEpicoJaUsado)
    assert um(real, "SELECT count(*) FROM epico WHERE lower(nome)='portal'") == 1


def test_donos_diferentes_podem_usar_o_mesmo_nome_ao_mesmo_tempo(real, monkeypatch):
    """A trava não pode serializar nem bloquear escopos diferentes: cada dono tem o seu nome."""
    outros = [real.auth.cadastrar(f"U{i}", f"u{i}@x.com", SENHA, SENHA) for i in range(N)]
    res = em_paralelo([lambda u=u: real.projetos.criar(u.id, "Portal") for u in outros])
    assert [t for t, _ in res] == ["ok"] * N
    assert um(real, "SELECT count(*) FROM projeto WHERE nome='Portal'") == N


# ---------- numeração: a trava é a defesa, não o banco ----------

def test_codigos_de_historia_simultaneos_sao_unicos_e_sequenciais(real, monkeypatch):
    projeto = real.projetos.criar(real.dono.id, "P")
    real.backlogs.criar_product(real.dono.id, projeto.id, "Product Backlog")
    forcar_janela(monkeypatch, historia_repository, "proximo_codigo", depois=False)
    res = em_paralelo(
        [lambda i=i: real.historias.criar(real.dono.id, projeto.id, "gerente", f"agir {i}", "ganhar") for i in range(N)]
    )
    assert [t for t, _ in res] == ["ok"] * N, [repr(v) for t, v in res if t == "erro"]
    codigos = sorted(int(v.codigo.removeprefix("SGR-")) for _, v in res)
    assert codigos == list(range(1, N + 1))


def test_codigos_de_historia_em_projetos_diferentes_nao_se_misturam(real):
    projetos = [real.projetos.criar(real.dono.id, f"P{i}") for i in range(3)]
    for p in projetos:
        real.backlogs.criar_product(real.dono.id, p.id, "Product Backlog")
    tarefas = [lambda p=p, i=i: real.historias.criar(real.dono.id, p.id, "g", f"a{i}", "b") for p in projetos for i in range(4)]
    res = em_paralelo(tarefas)
    assert [t for t, _ in res] == ["ok"] * 12, [repr(v) for t, v in res if t == "erro"]
    for p in projetos:
        cods = sorted(int(h.codigo.removeprefix("SGR-")) for _, h in res if h.projeto_id == p.id)
        assert cods == [1, 2, 3, 4]


def test_ordem_de_criterios_simultaneos_e_unica_e_sequencial(real, monkeypatch):
    projeto = real.projetos.criar(real.dono.id, "P")
    real.backlogs.criar_product(real.dono.id, projeto.id, "Product Backlog")
    historia = real.historias.criar(real.dono.id, projeto.id, "g", "a", "b")
    forcar_janela(monkeypatch, criterio_repository, "criar", depois=False)
    res = em_paralelo(
        [lambda i=i: real.criterios.criar(real.dono.id, historia.id, f"ctx {i}", "faço", "vejo") for i in range(N)]
    )
    assert [t for t, _ in res] == ["ok"] * N, [repr(v) for t, v in res if t == "erro"]
    assert sorted(v.ordem for _, v in res) == list(range(1, N + 1))
    assert [c.ordem for c in real.criterios.listar(real.dono.id, historia.id)] == list(range(1, N + 1))


def test_sprints_simultaneos_nao_tem_limite_de_quantidade(real):
    """Sem restrição de unicidade no nome do sprint, todos devem ser criados (contraponto do product)."""
    projeto = real.projetos.criar(real.dono.id, "P")
    res = em_paralelo(
        [lambda i=i: real.backlogs.criar_sprint(real.dono.id, projeto.id, f"Sprint {i}", date(2026, 1, 1), date(2026, 1, 15)) for i in range(N)]
    )
    assert [t for t, _ in res] == ["ok"] * N
    assert um(real, "SELECT count(*) FROM backlog WHERE tipo='SPRINT'") == N


# ---------- o caminho de recuperação do IntegrityError, sem depender de threads ----------
# Quando a checagem prévia perde a corrida, quem salva é o tratamento da exceção do banco.
# Aqui a checagem é forçada a "não ver nada" e o banco recusa: o resultado tem de ser o erro
# de domínio, e a sessão precisa continuar utilizável (o savepoint desfez só a gravação ruim).

def test_conflito_do_banco_vira_erro_de_dominio_em_cada_ponto(real, monkeypatch):
    projeto = real.projetos.criar(real.dono.id, "Portal")
    outro = real.projetos.criar(real.dono.id, "Outro")
    epico = real.epicos.criar(real.dono.id, projeto.id, "Catálogo")
    outro_epico = real.epicos.criar(real.dono.id, projeto.id, "Checkout")
    real.backlogs.criar_product(real.dono.id, projeto.id, "Product Backlog")
    real.auth.cadastrar("Ana", "ana@x.com", SENHA, SENHA)

    nada = lambda *a, **k: False  # noqa: E731 - a checagem prévia "não vê" o registro existente
    monkeypatch.setattr(projeto_repository, "existe_nome", nada)
    monkeypatch.setattr(epico_repository, "existe_nome", nada)
    monkeypatch.setattr(usuario_repository, "buscar_por_email", lambda *a, **k: None)
    original = backlog_repository.product_do_projeto
    chamadas = count()
    monkeypatch.setattr(
        backlog_repository, "product_do_projeto",
        lambda *a, **k: None if next(chamadas) == 0 else original(*a, **k),  # só a primeira (a checagem) falha
    )

    with pytest.raises(NomeJaUsado):
        real.projetos.criar(real.dono.id, "Portal")
    with pytest.raises(NomeJaUsado):
        real.projetos.atualizar(real.dono.id, outro.id, "Portal")
    with pytest.raises(NomeDeEpicoJaUsado):
        real.epicos.criar(real.dono.id, projeto.id, "Catálogo")
    with pytest.raises(NomeDeEpicoJaUsado):
        real.epicos.atualizar(real.dono.id, outro_epico.id, "Catálogo")
    with pytest.raises(EmailJaCadastrado):
        real.auth.cadastrar("Ana 2", "ana@x.com", SENHA, SENHA)
    with pytest.raises(ProductBacklogJaExiste):
        real.backlogs.criar_product(real.dono.id, projeto.id, "Outro")

    # nada foi gravado pelas tentativas perdedoras e o banco segue consistente
    assert um(real, "SELECT count(*) FROM projeto") == 2
    assert um(real, "SELECT count(*) FROM epico") == 2
    assert um(real, "SELECT count(*) FROM usuario") == 2
    assert um(real, "SELECT count(*) FROM backlog WHERE tipo='PRODUCT'") == 1
    assert um(real, "SELECT nome FROM projeto WHERE id=:i", i=outro.id) == "Outro"
