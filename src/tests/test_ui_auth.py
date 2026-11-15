"""Interface de conta e autenticação (issue #30), conforme o Storyboard 1 (Q-01 a Q-07)."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import text
from streamlit.proto.TextInput_pb2 import TextInput
from streamlit.testing.v1 import AppTest

from sgr.db import session as db_session
from sgr.services import autenticacao
from sgr.services.limitador import LimitadorTentativas
from sgr.ui import sessao as ses

APP = str(Path(__file__).resolve().parent.parent / "app.py")
EMAIL, SENHA = "ana@exemplo.com", "senha-segura-123"


# ---------- infraestrutura ----------

@pytest.fixture()
def banco(engine, test_url, monkeypatch):
    """Banco de testes com commits reais e tabelas limpas antes e depois."""
    monkeypatch.setenv("DATABASE_URL", test_url)
    db_session.get_engine.cache_clear()
    db_session._session_factory.cache_clear()
    monkeypatch.setattr(autenticacao, "_rounds", 4)
    monkeypatch.setattr(autenticacao, "_limitador", LimitadorTentativas())

    def limpar():
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE usuario RESTART IDENTITY CASCADE"))
            conn.execute(text("TRUNCATE registro_auditoria"))

    limpar()
    yield engine
    limpar()
    db_session.get_engine.cache_clear()
    db_session._session_factory.cache_clear()


@pytest.fixture()
def app(banco):
    return AppTest.from_file(APP, default_timeout=20).run()


@pytest.fixture()
def relogio(monkeypatch):
    """Relógio da sessão sob controle do teste."""

    class Relogio:
        agora = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)

        def avancar(self, **delta):
            self.agora += timedelta(**delta)

    r = Relogio()
    monkeypatch.setattr(ses, "agora", lambda: r.agora)
    return r


def _conta(nome="Ana", email=EMAIL):
    return autenticacao.cadastrar(nome, email, SENHA, SENHA)


def _entrar(at, email=EMAIL, senha=SENHA):
    at.text_input(key="entrar_email").input(email)
    at.text_input(key="entrar_senha").input(senha)
    at.button(key="btn_entrar").click()
    return at.run()


def _abrir_cadastro(at):
    at.button(key="btn_ir_cadastro").click()
    return at.run()


def _preencher(at, nome="Ana", email=EMAIL, senha=SENHA, conf=None, aceite=True):
    at.text_input(key="cadastro_nome").input(nome)
    at.text_input(key="cadastro_email").input(email)
    at.text_input(key="cadastro_senha").input(senha)
    at.text_input(key="cadastro_confirmacao").input(senha if conf is None else conf)
    at.checkbox(key="cadastro_politica").set_value(aceite)
    return at.run()


def _criar(at, **campos):
    at = _preencher(_abrir_cadastro(at), **campos)
    at.button(key="btn_cadastrar").click()
    return at.run()


def _legendas(at):
    return [c.value for c in at.caption]


def _erros(at):
    return " | ".join(e.value for e in at.error)


def _subtitulos(at):
    return [s.value for s in at.subheader]


def _mascarado(campo) -> bool:
    return campo.proto.type == TextInput.PASSWORD


def _logada(at):
    return at.session_state["usuario_autenticado"] is not None if "usuario_autenticado" in at.session_state else False


# ---------- Q-01 tela de entrada ----------

def test_sem_sessao_so_aparece_a_tela_de_entrada(app):
    assert not app.exception
    assert _subtitulos(app) == ["Entrar"]
    assert not app.tabs  # sem abas: "entrar" e "criar conta" são telas separadas
    assert len(app.sidebar.button) == 0  # sem menu lateral nem navegação
    assert app.text_input(key="entrar_email").placeholder == "seu@email.com"
    caps = _legendas(app)
    assert "Use o e-mail cadastrado na sua conta." in caps
    assert "Ainda não tem conta?" in caps
    assert any("LGPD" in c for c in caps)
    assert app.button(key="btn_ir_cadastro").label == "Criar conta"


def test_campo_de_senha_do_login_e_mascarado(app):
    assert _mascarado(app.text_input(key="entrar_senha"))


def test_entrar_abre_o_sistema_com_a_identificacao_do_usuario(app, banco):
    _conta()
    app = _entrar(app)
    assert not app.exception
    assert any("Olá, **Ana**" in m.value for m in app.markdown)
    assert any("AN" in t.value and "Ana" in t.value for t in app.sidebar.text)  # Q-05: nome e iniciais
    assert not [s for s in _subtitulos(app) if s == "Entrar"]


def test_login_com_dados_errados_mostra_erro_e_mantem_o_e_mail(app, banco):
    _conta()
    app = _entrar(app, senha="senha-errada-9")
    assert "incorretos" in _erros(app)
    assert app.text_input(key="entrar_email").value == EMAIL
    assert not any("Olá" in m.value for m in app.markdown)


def test_login_bloqueia_depois_de_muitas_tentativas(app, banco):
    _conta()
    for _ in range(5):
        app = _entrar(app, senha="senha-errada-9")
    app = _entrar(app)  # mesmo com a senha certa
    assert "Muitas tentativas" in _erros(app)
    assert not any("Olá" in m.value for m in app.markdown)


def test_login_com_caractere_invalido_e_credencial_invalida(app, banco):
    _conta()
    app = _entrar(app, email="ana\x00@exemplo.com")
    assert "incorretos" in _erros(app) and not app.exception


# ---------- Q-02 criar conta ----------

def test_tela_de_criar_conta_tem_os_campos_do_storyboard(app):
    app = _abrir_cadastro(app)
    assert _subtitulos(app) == ["Criar conta"]
    assert [t.label for t in app.text_input] == ["Nome ★", "E-mail ★", "Senha ★", "Confirmar senha ★"]
    assert app.text_input(key="cadastro_nome").placeholder == "Como você quer ser chamado"
    assert _mascarado(app.text_input(key="cadastro_senha"))
    assert _mascarado(app.text_input(key="cadastro_confirmacao"))
    assert app.checkbox(key="cadastro_politica").label == "Li e aceito a política de privacidade."
    assert "mínimo 8 caracteres · uma letra e um número" in _legendas(app)  # regra visível antes de digitar
    assert app.button(key="btn_cadastrar").label == "Criar conta"
    assert "Já tem conta?" in _legendas(app)


def test_ir_e_voltar_entre_entrar_e_criar_conta(app):
    app = _abrir_cadastro(app)
    app.button(key="btn_ir_entrar").click()
    app = app.run()
    assert _subtitulos(app) == ["Entrar"]


@pytest.mark.parametrize(
    "senha, nivel",
    [("abc", "fraca"), ("abcdefgh", "fraca"), ("senha1234", "boa"), ("Abcdefghij12", "forte")],
)
def test_medidor_de_forca_acompanha_a_senha(app, senha, nivel):
    app = _abrir_cadastro(app)
    app.text_input(key="cadastro_senha").input(senha)
    app = app.run()
    assert f"Força da senha: {nivel}" in _legendas(app)
    assert any("mínimo 8 caracteres" in c and ("✓" in c or "⚠" in c) for c in _legendas(app))


def test_medidor_marca_o_criterio_que_falta(app):
    app = _abrir_cadastro(app)
    app.text_input(key="cadastro_senha").input("abcdefgh")
    app = app.run()
    assert "✓ mínimo 8 caracteres · ✓ uma letra · ⚠ um número" in _legendas(app)


# ---------- Q-03 validação do cadastro ----------

def test_campo_obrigatorio_vazio_mostra_a_mensagem_e_nao_apaga_o_resto(app):
    app = _criar(app, nome="", email="maria@empresa.com.br", senha="senha-boa-123")
    assert "Informe seu nome." in _erros(app)
    assert app.text_input(key="cadastro_email").value == "maria@empresa.com.br"  # nada foi limpo
    assert app.text_input(key="cadastro_senha").value == "senha-boa-123"
    assert app.text_input(key="cadastro_confirmacao").value == "senha-boa-123"
    assert app.checkbox(key="cadastro_politica").value is True
    assert not _logada(app)


def test_email_ja_cadastrado_oferece_entrar_com_aquele_e_mail(app, banco):
    _conta(email="maria@empresa.com.br")
    app = _criar(app, email="maria@empresa.com.br")
    assert "Este e-mail já tem conta." in _erros(app)
    app.button(key="btn_entrar_com_email").click()
    app = app.run()
    assert _subtitulos(app) == ["Entrar"]
    assert app.text_input(key="entrar_email").value == "maria@empresa.com.br"


def test_senhas_diferentes(app):
    app = _criar(app, senha="senha-boa-123", conf="senha-boa-12")
    assert "As senhas não conferem." in _erros(app)
    assert not _logada(app)


@pytest.mark.parametrize("senha", ["curta1", "somente-letras", "12345678"])
def test_senha_fora_da_regra_explica_como_corrigir(app, senha):
    app = _criar(app, senha=senha)
    assert "pelo menos 8 caracteres, uma letra e um número" in _erros(app)


def test_sem_aceitar_a_politica_nao_cria_a_conta(app, banco):
    app = _criar(app, aceite=False)
    assert "Aceite a política de privacidade" in _erros(app)
    assert not _logada(app)
    with banco.connect() as c:
        assert c.execute(text("SELECT count(*) FROM usuario")).scalar_one() == 0


def test_varios_erros_aparecem_de_uma_vez_cada_um_no_seu_campo(app):
    app = _criar(app, nome="", email="invalido", senha="abc", aceite=False)
    texto = _erros(app)
    for esperado in ("Informe seu nome.", "e-mail válido", "pelo menos 8", "Aceite a política"):
        assert esperado in texto


def test_caractere_invalido_no_cadastro_nao_derruba_a_tela(app):
    app = _criar(app, nome="Ana\x00")
    assert not app.exception and "caractere inválido" in _erros(app)


# ---------- Q-04 conta criada ----------

def test_conta_criada_ja_inicia_a_sessao_e_mostra_a_confirmacao(app, banco):
    app = _criar(app)
    assert not app.exception
    assert "✓ Conta criada." in _subtitulos(app)
    assert any("Você já pode usar o sistema." in m.value for m in app.markdown)
    assert any("projetos e backlogs aparecem vazios" in i.value for i in app.info)
    assert app.button(key="btn_comecar_agora").label == "Começar agora"
    assert app.session_state["usuario_autenticado"].email == EMAIL  # autenticada sem novo login
    for campo in ("cadastro_senha", "cadastro_confirmacao"):  # a senha não fica no estado
        assert campo not in app.session_state


def test_conta_criada_registra_o_aceite_da_politica(app, banco):
    _criar(app)
    with banco.connect() as c:
        valor = c.execute(text("SELECT valor_posterior FROM registro_auditoria WHERE entidade='usuario'")).scalar_one()
    assert valor["politica_privacidade_aceita"] is True


def test_comecar_agora_leva_aos_projetos_com_boas_vindas(app, banco):
    app = _criar(app, nome="Maria Souza", email="maria@empresa.com.br")
    app.button(key="btn_comecar_agora").click()
    app = app.run()
    assert not app.exception
    assert not _subtitulos(app) == ["✓ Conta criada."]
    assert [t.value for t in app.toast] == ["Bem-vindo, Maria."]
    assert any(t.value == "Projetos" for t in app.title)  # caiu na página de projetos


# ---------- Q-05 sessão autenticada ----------

def test_sidebar_mostra_a_sessao_e_o_menu_da_conta(app, banco, relogio):
    _conta()
    app = _entrar(app)
    assert any(c.startswith("Sessão iniciada às ") and "expira após 8 horas de inatividade" in c
               for c in [c.value for c in app.sidebar.caption])
    assert app.sidebar.button(key="btn_minha_conta").label == "Minha conta"
    assert app.sidebar.button(key="btn_sair").label == "Sair"


def test_horario_da_sessao_vem_do_relogio(relogio):
    ses.st.session_state.clear()
    ses.st.session_state["sessao_iniciada_em"] = datetime(2026, 11, 14, 9, 14, tzinfo=timezone.utc)
    assert "Sessão iniciada às 09:14" in ses.texto_da_sessao()


# ---------- Q-06 guarda de acesso ----------

def test_sessao_parada_por_mais_de_8_horas_expira(app, banco, relogio):
    _conta()
    app = _entrar(app)
    relogio.avancar(hours=8, seconds=1)
    app = app.run()
    assert _subtitulos(app) == ["◷ Sua sessão expirou"]
    assert any("8 horas de inatividade" in m.value for m in app.markdown)
    assert "usuario_autenticado" not in app.session_state  # o usuário não fica mais no estado
    assert not any("Olá" in m.value for m in app.markdown)


def test_exatamente_8_horas_ainda_vale(app, banco, relogio):
    _conta()
    app = _entrar(app)
    relogio.avancar(hours=8)
    app = app.run()
    assert any("Olá, **Ana**" in m.value for m in app.markdown)


def test_atividade_renova_o_prazo_da_sessao(app, banco, relogio):
    _conta()
    app = _entrar(app)
    relogio.avancar(hours=7, minutes=59)
    app = app.run()  # atividade a cada quase 8 horas
    relogio.avancar(hours=7, minutes=59)
    app = app.run()
    assert any("Olá, **Ana**" in m.value for m in app.markdown)  # 15h59 desde o login, mas ativa


def test_entrar_novamente_volta_com_o_e_mail_preenchido(app, banco, relogio):
    _conta()
    app = _entrar(app)
    relogio.avancar(hours=9)
    app = app.run()
    app.button(key="btn_entrar_novamente").click()
    app = app.run()
    assert _subtitulos(app) == ["Entrar"]
    assert app.text_input(key="entrar_email").value == EMAIL
    app = _entrar(app)  # e já entra de novo
    assert any("Olá, **Ana**" in m.value for m in app.markdown)


def test_continuar_como_outro_usuario_nao_traz_o_e_mail_anterior(app, banco, relogio):
    _conta()
    app = _entrar(app)
    relogio.avancar(hours=9)
    app = app.run()
    app.button(key="btn_outro_usuario").click()
    app = app.run()
    assert app.text_input(key="entrar_email").value == ""
    assert ses.st.session_state.get("ultimo_email") is None or "ultimo_email" not in app.session_state


def test_acesso_direto_a_pagina_interna_sem_sessao_explica_e_leva_a_entrada(banco, monkeypatch):
    monkeypatch.setattr(ses, "caminho_solicitado", lambda: "projetos")
    app = AppTest.from_file(APP, default_timeout=20).run()
    assert _subtitulos(app) == ["🔒 Você precisa entrar para acessar esta página"]
    assert any("exige autenticação" in m.value for m in app.markdown)
    assert any("levado de volta" in c for c in _legendas(app))
    app.button(key="btn_entrar_acesso").click()
    app = app.run()
    assert _subtitulos(app) == ["Entrar"]  # o aviso não volta a cada execução
    app = app.run()
    assert _subtitulos(app) == ["Entrar"]


def test_pagina_inicial_sem_endereco_interno_mostra_a_entrada_normal(banco, monkeypatch):
    monkeypatch.setattr(ses, "caminho_solicitado", lambda: "")
    assert _subtitulos(AppTest.from_file(APP, default_timeout=20).run()) == ["Entrar"]


def test_endereco_desconhecido_nao_e_tratado_como_pagina_interna(banco, monkeypatch):
    monkeypatch.setattr(ses, "caminho_solicitado", lambda: "qualquer-coisa")
    assert _subtitulos(AppTest.from_file(APP, default_timeout=20).run()) == ["Entrar"]


@pytest.mark.parametrize(
    "url, caminho",
    [(None, ""), ("", ""), ("http://localhost:8501", ""), ("http://localhost:8501/", ""),
     ("http://localhost:8501/projetos", "projetos"), ("https://x.com/projetos/?a=1#b", "projetos"),
     ("http://localhost:8501/backlogs?x=y", "backlogs")],
)
def test_caminho_da_url(url, caminho):
    assert ses.caminho_da_url(url) == caminho


def test_pagina_protegida_recusa_acesso_sem_login(banco):
    """Defesa em profundidade: mesmo chamada diretamente, a página inicial exige login."""

    def script():
        from sgr.ui.pagina_inicio import pagina_inicio

        pagina_inicio()

    at = AppTest.from_function(script, default_timeout=20).run()
    assert any("Faça login" in e.value for e in at.error)
    assert not any("Olá" in m.value for m in at.markdown)


def test_pagina_protegida_tambem_recusa_sessao_expirada(banco, relogio):
    def script():
        from sgr.ui.pagina_inicio import pagina_inicio

        pagina_inicio()

    at = AppTest.from_function(script, default_timeout=20)
    at.session_state["usuario_autenticado"] = _conta()
    at.run()
    relogio.avancar(hours=9)
    at = at.run()
    assert any("Faça login" in e.value for e in at.error)


# ---------- Q-07 sair ----------

def _abrir_dialogo(nome):
    """Abre um diálogo direto (o AppTest reexecuta o script inteiro a cada interação)."""

    def script(funcao):
        from sgr.ui import conta

        getattr(conta, funcao)()

    return AppTest.from_function(script, args=(nome,), default_timeout=20)


def test_sair_pede_confirmacao_e_cancelar_mantem_a_sessao(banco):
    at = _abrir_dialogo("confirmar_saida")
    at.session_state["usuario_autenticado"] = _conta()
    at.run()
    assert any("precisará entrar novamente" in m.value for m in at.markdown)
    at.button(key="btn_cancelar_saida").click()
    at = at.run()
    assert "usuario_autenticado" in at.session_state


def test_confirmar_sair_encerra_a_sessao_e_limpa_o_estado(banco):
    at = _abrir_dialogo("confirmar_saida")
    at.session_state["usuario_autenticado"] = _conta()
    at.session_state["entrar_senha"] = "resto-de-formulario"
    at.run()
    at.button(key="btn_confirmar_saida").click()
    at = at.run()
    assert "usuario_autenticado" not in at.session_state
    assert "entrar_senha" not in at.session_state  # nada vaza para o próximo usuário
    assert at.session_state["motivo_de_acesso"] == "saiu"


def test_depois_de_sair_aparece_o_aviso_uma_unica_vez(banco):
    at = AppTest.from_file(APP, default_timeout=20)
    at.session_state["motivo_de_acesso"] = "saiu"
    at = at.run()
    assert [t.value for t in at.toast] == ["Você saiu do sistema."]
    assert _subtitulos(at) == ["Entrar"]
    assert [t.value for t in at.run().toast] == []


def test_sair_pelo_app_abre_a_confirmacao(app, banco):
    _conta()
    app = _entrar(app)
    app.sidebar.button(key="btn_sair").click()
    app = app.run()
    assert not app.exception  # o diálogo abre; a sessão segue válida até confirmar
    assert "usuario_autenticado" in app.session_state


def test_minha_conta_mostra_nome_e_e_mail_somente_leitura(banco):
    at = _abrir_dialogo("dialogo_minha_conta")
    at.session_state["usuario_autenticado"] = _conta("Maria Souza", "maria@empresa.com.br")
    at.run()
    assert (at.text_input(key="conta_nome").value, at.text_input(key="conta_nome").disabled) == ("Maria Souza", True)
    assert (at.text_input(key="conta_email").value, at.text_input(key="conta_email").disabled) == ("maria@empresa.com.br", True)


def test_politica_de_privacidade_descreve_o_que_e_coletado():
    def script():
        from sgr.ui.politica import ler_politica

        ler_politica()

    at = AppTest.from_function(script, default_timeout=20).run()
    texto = " ".join(m.value for m in at.markdown)
    assert "hash" in texto and "Finalidade" in texto
    assert any("provisório" in c.value for c in at.caption)


@pytest.mark.parametrize(
    "nome, iniciais",
    [("Maria", "MA"), ("Maria Souza", "MS"), ("ana maria de souza lima", "AL"), ("  João  ", "JO"), ("X", "X"), ("", "?")],
)
def test_iniciais_do_avatar(nome, iniciais):
    from sgr.ui.conta import iniciais as f

    assert f(nome) == iniciais
