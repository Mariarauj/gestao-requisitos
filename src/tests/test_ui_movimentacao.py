"""Fluxo de tela das histórias do backlog e da movimentação (Storyboard 4: Q-27 a Q-29, requisito 8)."""
from datetime import date

import pytest
from sqlalchemy import text
from streamlit.testing.v1 import AppTest

from sgr.services import backlogs, criterios, epicos, historias, priorizacao
from sgr.services.backlog_service import BacklogNaoEncontrado, SprintEncerrado
from tests.test_ui_backlogs import ctx  # noqa: F401  (fixture: Ana com um projeto)


def _script():
    from sgr.ui.pagina_backlogs import pagina_backlogs

    pagina_backlogs()


def _script_mover(origem_id, historias_ids):
    """Chama o diálogo direto em todo run (o AppTest reexecuta o script inteiro a cada clique)."""
    from sgr.services import backlogs, historias
    from sgr.ui import backlog_historias as bh
    from sgr.ui.sessao import usuario_logado

    u = usuario_logado()
    origem = backlogs.obter(u.id, origem_id)
    conj = backlogs.listar(u.id, origem.projeto_id)
    todos = ([conj.product] if conj.product else []) + conj.sprints
    sel = [h for h in historias.listar(u.id, origem.projeto_id, backlog_id=origem_id) if h.id in historias_ids]
    bh._dialogo_mover(u.id, origem, todos, sel)


def _abrir(usuario, backlog_id):
    """Abre o detalhe do backlog como se o usuário tivesse clicado em "Abrir" na lista."""
    at = AppTest.from_function(_script, default_timeout=20)
    at.session_state["usuario_autenticado"] = usuario
    try:  # a página descarta o backlog aberto se o projeto escolhido não for o dele
        at.session_state["backlogs_projeto_id"] = backlogs.obter(usuario.id, backlog_id).projeto_id
    except BacklogNaoEncontrado:
        pass
    at.session_state["backlog_aberto"] = backlog_id
    return at.run()


def _mover(usuario, origem_id, ids):
    at = AppTest.from_function(_script_mover, args=(origem_id, ids), default_timeout=20)
    at.session_state["usuario_autenticado"] = usuario
    return at.run()


def _cenario(ctx):
    """Product com 3 histórias, Sprint 12 (em andamento), Sprint 13 (planejado), Sprint 11 (encerrado)."""
    ana, proj = ctx
    pb = backlogs.criar_product(ana.id, proj.id, "Product Backlog", None)
    s12 = backlogs.criar_sprint(ana.id, proj.id, "Sprint 12", date(2026, 10, 1), date(2026, 10, 14))
    s13 = backlogs.criar_sprint(ana.id, proj.id, "Sprint 13", date(2026, 10, 15), date(2026, 10, 28))
    s11 = backlogs.criar_sprint(ana.id, proj.id, "Sprint 11", date(2026, 9, 17), date(2026, 9, 30))
    epico = epicos.criar(ana.id, proj.id, "Acompanhamento")
    h1 = historias.criar(ana.id, proj.id, "cliente", "acompanhar o pedido", "saber o status",
                         story_points=5, moscow="M", epicos_ids=[epico.id])
    h2 = historias.criar(ana.id, proj.id, "cliente", "receber alerta", "não perder a entrega",
                         story_points=3, moscow="S")
    h3 = historias.criar(ana.id, proj.id, "gerente", "exportar relatório", "analisar fora",
                         story_points=8, moscow="C")
    priorizacao.definir_rice(ana.id, h1.id, 100, 2, 80, 5)  # nota 32
    return ana, proj, pb, (s12, s13, s11), epico, (h1, h2, h3)


def _encerrar(engine, backlog_id):
    with engine.begin() as conn:
        conn.execute(text("UPDATE backlog SET estado='ENCERRADO' WHERE id=:i"), {"i": backlog_id})


def _codigos(at):
    return [m.value.split("**")[1] for m in at.markdown if m.value.startswith("**SGR-")]


# ---------- Q-27: product backlog ----------

def test_product_backlog_lista_historias_com_pontos_moscow_rice_e_epico(ctx, engine):
    ana, proj, pb, _, _, _ = _cenario(ctx)
    at = _abrir(ana, pb.id)
    assert not at.exception
    assert any(m.value.startswith("**SGR-1**") and "Acompanhamento" in m.value for m in at.markdown)
    legendas = [c.value for c in at.caption]
    assert "5 pts · M · RICE 32" in legendas
    assert "3 pts · S · RICE pendente" in legendas
    assert any("Como um cliente, eu quero acompanhar o pedido, para saber o status" in m.value for m in at.markdown)


def test_painel_de_sprints_mostra_estado_e_abre_o_sprint(ctx, engine):
    ana, proj, pb, (s12, s13, s11), _, _ = _cenario(ctx)
    _encerrar(engine, s11.id)
    at = _abrir(ana, pb.id)
    texto = " ".join(c.value for c in at.caption)
    assert "01/10/2026 a 14/10/2026 · Planejado" in texto and "17/09/2026 a 30/09/2026 · Encerrado" in texto
    at.button(key=f"painel_abrir_{s13.id}").click()
    at = at.run()
    assert at.session_state["backlog_aberto"] == s13.id
    assert at.title[1].value == "Sprint 13"


def test_selecionar_mostra_a_barra_e_limpar_selecao_desmarca(ctx):
    ana, proj, pb, _, _, (h1, h2, _) = _cenario(ctx)
    at = _abrir(ana, pb.id)
    assert not [b for b in at.button if b.key.startswith("btn_mover_")]  # sem seleção, sem barra
    at.checkbox(key=f"sel_{pb.id}_0_{h1.id}").check()
    at.checkbox(key=f"sel_{pb.id}_0_{h2.id}").check()
    at = at.run()
    assert any("2 histórias selecionadas" in m.value for m in at.markdown)
    assert at.button(key=f"btn_mover_{pb.id}").label == "Mover para..."
    at.button(key=f"btn_limpar_selecao_{pb.id}").click()
    at = at.run()
    assert not any("selecionada" in m.value for m in at.markdown)
    assert not at.checkbox(key=f"sel_{pb.id}_1_{h1.id}").value


def test_filtro_por_moscow_epico_e_limpar_filtros(ctx):
    ana, proj, pb, _, epico, (h1, h2, h3) = _cenario(ctx)
    at = _abrir(ana, pb.id)
    assert _codigos(at) == [h1.codigo, h2.codigo, h3.codigo]
    at.selectbox(key=f"flt_moscow_{pb.id}").select("S")
    at = at.run()
    assert _codigos(at) == [h2.codigo]
    at.selectbox(key=f"flt_moscow_{pb.id}").select(None)
    at.selectbox(key=f"flt_epico_{pb.id}").select(epico.id)
    at = at.run()
    assert _codigos(at) == [h1.codigo]
    at.selectbox(key=f"flt_moscow_{pb.id}").select("W")
    at = at.run()
    assert _codigos(at) == [] and any("Nenhuma história com esses filtros" in c.value for c in at.caption)
    at.button(key=f"btn_limpar_filtros_{pb.id}").click()
    at = at.run()
    assert _codigos(at) == [h1.codigo, h2.codigo, h3.codigo]


def test_ordenar_por_pontos_rice_e_moscow(ctx):
    ana, proj, pb, _, _, (h1, h2, h3) = _cenario(ctx)  # pontos 5, 3, 8; só h1 tem RICE
    at = _abrir(ana, pb.id)
    at.selectbox(key=f"flt_ordem_{pb.id}").select("pontos")
    assert _codigos(at.run()) == [h3.codigo, h1.codigo, h2.codigo]
    at.selectbox(key=f"flt_ordem_{pb.id}").select("rice")
    assert _codigos(at.run()) == [h1.codigo, h2.codigo, h3.codigo]  # sem RICE por último
    at.selectbox(key=f"flt_ordem_{pb.id}").select("moscow")
    assert _codigos(at.run()) == [h1.codigo, h2.codigo, h3.codigo]  # M, S, C


def test_backlog_vazio_mostra_aviso_e_o_painel_de_sprints(ctx):
    ana, proj = ctx
    pb = backlogs.criar_product(ana.id, proj.id, "PB", None)
    backlogs.criar_sprint(ana.id, proj.id, "Sprint 1", date(2026, 10, 1), date(2026, 10, 14))
    at = _abrir(ana, pb.id)
    assert any("Nenhuma história neste backlog" in c.value for c in at.caption)
    assert any(m.value == "**Sprint 1**" for m in at.markdown)


# ---------- Q-28: diálogo de movimentação ----------

def test_dialogo_lista_destinos_marca_encerrado_e_explica_que_nada_se_perde(ctx, engine):
    ana, proj, pb, (s12, s13, s11), _, (h1, h2, _) = _cenario(ctx)
    _encerrar(engine, s11.id)
    at = _mover(ana, pb.id, [h1.id, h2.id])
    assert not at.exception
    opcoes = at.radio(key=f"mover_destino_{pb.id}").options
    assert len(opcoes) == 2 and all("Sprint 1" in o and "Planejado" in o for o in opcoes)
    assert all("Sprint 11" not in o for o in opcoes)  # encerrado não é opção
    assert any("Sprint 11 · Encerrado (somente leitura)" in c.value for c in at.caption)
    assert any(h1.codigo in c.value and h2.codigo in c.value for c in at.caption)
    assert any("Mover não apaga nada" in i.value for i in at.info)


def test_mover_para_sprint_preserva_dados_avisa_e_atualiza_contadores(ctx):
    ana, proj, pb, (s12, s13, _), epico, (h1, h2, h3) = _cenario(ctx)
    criterios.criar(ana.id, h1.id, "estou logado", "abro o pedido", "vejo o status")
    at = _mover(ana, pb.id, [h1.id, h2.id])
    at.radio(key=f"mover_destino_{pb.id}").set_value(s13.id)
    at.button(key=f"btn_confirmar_mover_{pb.id}").click()
    at = at.run()
    assert not at.exception
    assert at.session_state["aviso_backlog"] == "2 histórias movidas para Sprint 13. Agora ele tem 2 histórias."
    assert backlogs.obter(ana.id, s13.id).historias == 2 and backlogs.obter(ana.id, pb.id).historias == 1
    movida = historias.obter(ana.id, h1.id)
    assert (movida.backlog_id, movida.story_points, movida.moscow, movida.rice) == (s13.id, 5, "M", 32)
    assert [e.id for e in movida.epicos] == [epico.id] and len(movida.criterios) == 1  # nada se perde
    assert at.session_state["geracao_selecao_%d" % pb.id] == 1  # seleção limpa


def test_devolver_historia_do_sprint_ao_product_backlog(ctx):
    ana, proj, pb, (s12, s13, _), _, (h1, _, _) = _cenario(ctx)
    backlogs.mover_historias(ana.id, [h1.id], s13.id)
    at = _mover(ana, s13.id, [h1.id])
    destinos = at.radio(key=f"mover_destino_{s13.id}").options
    assert not any("Sprint 13" in d for d in destinos)  # o próprio backlog não é destino
    at.radio(key=f"mover_destino_{s13.id}").set_value(pb.id)
    at.button(key=f"btn_confirmar_mover_{s13.id}").click()
    at = at.run()
    assert at.session_state["aviso_backlog"].startswith("1 história movida para Product Backlog.")
    assert historias.obter(ana.id, h1.id).backlog_id == pb.id


def test_mover_de_um_sprint_para_outro(ctx):
    ana, proj, pb, (s12, s13, _), _, (h1, _, _) = _cenario(ctx)
    backlogs.mover_historias(ana.id, [h1.id], s12.id)
    at = _mover(ana, s12.id, [h1.id])
    at.radio(key=f"mover_destino_{s12.id}").set_value(s13.id)
    at.button(key=f"btn_confirmar_mover_{s12.id}").click()
    at.run()
    assert historias.obter(ana.id, h1.id).backlog_id == s13.id


def test_cancelar_nao_move(ctx):
    ana, proj, pb, _, _, (h1, _, _) = _cenario(ctx)
    at = _mover(ana, pb.id, [h1.id])
    at.button(key=f"btn_cancelar_mover_{pb.id}").click()
    at.run()
    assert historias.obter(ana.id, h1.id).backlog_id == pb.id


def test_sem_destino_disponivel_orienta_a_criar_sprint(ctx):
    ana, proj = ctx
    pb = backlogs.criar_product(ana.id, proj.id, "PB", None)
    h = historias.criar(ana.id, proj.id, "a", "b", "c")
    at = _mover(ana, pb.id, [h.id])
    assert any("Crie um sprint backlog" in w.value for w in at.warning)
    assert not [b for b in at.button if b.key.startswith("btn_confirmar_mover_")]


def test_erro_do_servico_aparece_no_dialogo_e_nada_e_movido(ctx, monkeypatch):
    ana, proj, pb, (s12, _, _), _, (h1, _, _) = _cenario(ctx)

    def recusa(*args, **kwargs):
        raise SprintEncerrado("Sprint 12", destino=True)

    monkeypatch.setattr(backlogs, "mover_historias", recusa)
    at = _mover(ana, pb.id, [h1.id])
    at.radio(key=f"mover_destino_{pb.id}").set_value(s12.id)
    at.button(key=f"btn_confirmar_mover_{pb.id}").click()
    at = at.run()
    assert any("está encerrado (somente leitura)" in e.value for e in at.error)
    assert "aviso_backlog" not in at.session_state
    assert historias.obter(ana.id, h1.id).backlog_id == pb.id


# ---------- Q-29: sprint backlog ----------

def test_sprint_lista_historias_e_permite_selecionar_para_devolver(ctx):
    ana, proj, pb, (s12, s13, _), _, (h1, h2, _) = _cenario(ctx)
    backlogs.mover_historias(ana.id, [h1.id, h2.id], s13.id)
    at = _abrir(ana, s13.id)
    assert _codigos(at) == [h1.codigo, h2.codigo]
    assert not [b for b in at.button if b.key.startswith("painel_abrir_")]  # painel só no product
    at.checkbox(key=f"sel_{s13.id}_0_{h2.id}").check()
    at = at.run()
    assert any("1 história selecionada" in m.value for m in at.markdown)
    assert at.button(key=f"btn_mover_{s13.id}").label == "Mover para..."


def test_sprint_encerrado_e_somente_leitura(ctx, engine):
    ana, proj, pb, (s12, s13, s11), _, (h1, _, _) = _cenario(ctx)
    backlogs.mover_historias(ana.id, [h1.id], s11.id)
    _encerrar(engine, s11.id)
    at = _abrir(ana, s11.id)
    assert any("Sprint encerrado (somente leitura)" in i.value for i in at.info)
    assert _codigos(at) == [h1.codigo]
    assert at.checkbox(key=f"sel_{s11.id}_0_{h1.id}").disabled
    assert not [b for b in at.button if b.key.startswith("btn_mover_")]


def test_historias_de_outro_usuario_nao_aparecem(ctx, engine):
    ana, proj, pb, _, _, _ = _cenario(ctx)
    from sgr.services import autenticacao

    bia = autenticacao.cadastrar("Bia", "bia@x.com", "senha-segura-123", "senha-segura-123")
    at = _abrir(bia, pb.id)  # backlog que Bia não enxerga: volta para a lista, sem exibir nada
    assert not at.exception and _codigos(at) == []
