"""CRUD de histórias de usuário e vínculo com épicos (requisitos 7, 9 e 11).

Regras:
- a história nasce no product backlog do projeto; sem product backlog, não pode ser criada;
- papel, ação e benefício são campos separados e obrigatórios; a frase padrão
  "Como um [papel], eu quero [ação], para [benefício]" é montada a partir deles;
- o código legível (SGR-1, SGR-2...) é gerado pelo sistema, é único no projeto e não muda
  quando a história é movida;
- story points e MoSCoW são aceitos aqui por existirem no formulário da história; os valores
  válidos também são garantidos pelo banco. A nota RICE fica fora deste serviço;
- uma história pode ter vários épicos, sempre do mesmo projeto;
- quem tem acesso ao projeto gerencia as histórias; fora dele, tudo é "não encontrado";
- toda escrita gera registro de auditoria.
"""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from typing import Callable, Iterable

from sqlalchemy.orm import Session

from sgr.db.session import get_session
from sgr.models import Historia
from sgr.repositories import (
    auditoria_repository,
    backlog_repository,
    criterio_repository,
    epico_repository,
    historia_repository,
    projeto_repository,
)
from sgr.services.auth_service import ErroDeValidacao
from sgr.services.projeto_service import ProjetoNaoEncontrado

PAPEL_MAX = 120
ACAO_MAX = 200
BENEFICIO_MAX = 200
STORY_POINTS = (0, 1, 2, 3, 5, 8, 13, 21, 34, 55)
MOSCOW = ("M", "S", "C", "W")
MOSCOW_PADRAO = "S"


@dataclass(frozen=True)
class EpicoRef:
    id: int
    nome: str


@dataclass(frozen=True)
class CriterioDados:
    id: int
    historia_id: int
    contexto: str
    acao: str
    resultado: str
    ordem: int

    @property
    def frase(self) -> str:
        return f"Dado {self.contexto}, quando {self.acao}, então {self.resultado}"


@dataclass(frozen=True)
class HistoriaDados:
    id: int
    projeto_id: int
    backlog_id: int
    backlog_nome: str
    backlog_tipo: str
    codigo: str
    papel: str
    acao: str
    beneficio: str
    story_points: int | None
    moscow: str
    epicos: tuple[EpicoRef, ...] = ()
    criterios_total: int = 0
    criterios: tuple[CriterioDados, ...] = field(default=(), compare=False)  # só em obter()

    @property
    def frase(self) -> str:
        return f"Como um {self.papel}, eu quero {self.acao}, para {self.beneficio}"


@dataclass(frozen=True)
class InventarioHistoria:
    """O que será removido junto com a história (aviso da confirmação de exclusão)."""

    criterios: int
    epicos: int


class HistoriaNaoEncontrada(Exception):
    def __init__(self) -> None:
        super().__init__("História não encontrada.")


class ProductBacklogInexistente(Exception):
    def __init__(self) -> None:
        super().__init__(
            "Este projeto ainda não tem product backlog. Crie o product backlog "
            "antes de cadastrar histórias."
        )


def _validar(
    papel: str | None,
    acao: str | None,
    beneficio: str | None,
    story_points: int | None,
    moscow: str | None,
) -> tuple[str, str, str, int | None, str | None]:
    papel, acao, beneficio = (papel or "").strip(), (acao or "").strip(), (beneficio or "").strip()
    erros: dict[str, str] = {}
    for campo, valor, rotulo, limite in (
        ("papel", papel, "o papel", PAPEL_MAX),
        ("acao", acao, "a ação", ACAO_MAX),
        ("beneficio", beneficio, "o benefício", BENEFICIO_MAX),
    ):
        if not valor:
            erros[campo] = f"Informe {rotulo}."
        elif len(valor) > limite:
            erros[campo] = f"Este campo deve ter no máximo {limite} caracteres."
    if story_points is not None and (
        isinstance(story_points, bool) or story_points not in STORY_POINTS
    ):
        valores = ", ".join(str(v) for v in STORY_POINTS)
        erros["story_points"] = f"Story points inválido. Valores aceitos: {valores}."
    if moscow is not None:
        moscow = moscow.strip().upper()
        if moscow not in MOSCOW:
            erros["moscow"] = "Etiqueta MoSCoW inválida. Valores aceitos: M, S, C, W."
    if erros:
        raise ErroDeValidacao(erros)
    return papel, acao, beneficio, story_points, moscow


def _snapshot(h: Historia, epicos: Iterable[int]) -> dict:
    return {
        "codigo": h.codigo,
        "papel": h.papel,
        "acao": h.acao,
        "beneficio": h.beneficio,
        "story_points": h.story_points,
        "moscow": h.moscow,
        "backlog_id": h.backlog_id,
        "epicos": sorted(epicos),
    }


class HistoriaService:
    def __init__(
        self, sessao: Callable[[], AbstractContextManager[Session]] = get_session
    ) -> None:
        self._sessao = sessao

    # ---------- leitura ----------

    def listar(
        self,
        usuario_id: int,
        projeto_id: int,
        *,
        backlog_id: int | None = None,
        epico_id: int | None = None,
        moscow: str | None = None,
    ) -> list[HistoriaDados]:
        """Histórias do projeto, da mais antiga para a mais nova, com filtros opcionais."""
        if moscow is not None:
            moscow = moscow.strip().upper()
            if moscow not in MOSCOW:
                raise ErroDeValidacao({"moscow": "Etiqueta MoSCoW inválida. Valores aceitos: M, S, C, W."})
        with self._sessao() as sessao:
            self._projeto(sessao, usuario_id, projeto_id)
            historias = historia_repository.listar(sessao, projeto_id, backlog_id, epico_id, moscow)
            return self._dados(sessao, historias)

    def obter(self, usuario_id: int, historia_id: int) -> HistoriaDados:
        """História completa, com os critérios de aceitação em ordem."""
        with self._sessao() as sessao:
            historia = self._acessivel(sessao, usuario_id, historia_id)
            dados = self._dados(sessao, [historia])[0]
            criterios = tuple(
                CriterioDados(c.id, c.historia_id, c.contexto, c.acao, c.resultado, c.ordem)
                for c in criterio_repository.listar(sessao, historia.id)
            )
            return HistoriaDados(**{**dados.__dict__, "criterios": criterios})

    def inventario(self, usuario_id: int, historia_id: int) -> InventarioHistoria:
        with self._sessao() as sessao:
            historia = self._acessivel(sessao, usuario_id, historia_id)
            criterios = historia_repository.contar_criterios(sessao, [historia.id])[historia.id]
            epicos = len(epico_repository.ids_vinculados(sessao, historia.id))
            return InventarioHistoria(criterios=criterios, epicos=epicos)

    # ---------- criar ----------

    def criar(
        self,
        usuario_id: int,
        projeto_id: int,
        papel: str | None,
        acao: str | None,
        beneficio: str | None,
        story_points: int | None = None,
        moscow: str | None = MOSCOW_PADRAO,
        epicos_ids: Iterable[int] = (),
    ) -> HistoriaDados:
        papel, acao, beneficio, story_points, moscow = _validar(
            papel, acao, beneficio, story_points, moscow or MOSCOW_PADRAO
        )
        epicos = set(epicos_ids)
        with self._sessao() as sessao:
            self._projeto(sessao, usuario_id, projeto_id)
            product = backlog_repository.product_do_projeto(sessao, projeto_id)
            if product is None:
                raise ProductBacklogInexistente()
            self._exigir_epicos_do_projeto(sessao, projeto_id, epicos)
            historia = historia_repository.criar(
                sessao,
                projeto_id=projeto_id,
                backlog_id=product.id,
                codigo=historia_repository.proximo_codigo(sessao, projeto_id),
                papel=papel,
                acao=acao,
                beneficio=beneficio,
                story_points=story_points,
                moscow=moscow,
            )
            epico_repository.vincular(sessao, historia.id, epicos)
            self._auditar(sessao, usuario_id, historia, "CRIAR", posterior=_snapshot(historia, epicos))
            return self._dados(sessao, [historia])[0]

    # ---------- atualizar ----------

    def atualizar(
        self,
        usuario_id: int,
        historia_id: int,
        papel: str | None,
        acao: str | None,
        beneficio: str | None,
        story_points: int | None = None,
        moscow: str | None = None,
    ) -> HistoriaDados:
        """Atualiza os campos da história como um formulário: story_points sempre é gravado
        (None remove a estimativa); moscow None mantém a etiqueta atual. Código e backlog
        não mudam (mover é outra operação)."""
        papel, acao, beneficio, story_points, moscow = _validar(
            papel, acao, beneficio, story_points, moscow
        )
        with self._sessao() as sessao:
            historia = self._acessivel(sessao, usuario_id, historia_id)
            epicos = epico_repository.ids_vinculados(sessao, historia.id)
            anterior = _snapshot(historia, epicos)
            historia.papel, historia.acao, historia.beneficio = papel, acao, beneficio
            historia.story_points = story_points
            if moscow is not None:
                historia.moscow = moscow
            sessao.flush()
            posterior = _snapshot(historia, epicos)
            if posterior != anterior:
                self._auditar(sessao, usuario_id, historia, "ALTERAR", anterior, posterior)
            return self._dados(sessao, [historia])[0]

    # ---------- vínculo com épicos ----------

    def definir_epicos(
        self, usuario_id: int, historia_id: int, epicos_ids: Iterable[int]
    ) -> HistoriaDados:
        """Substitui o conjunto de épicos da história (o que o formulário envia)."""
        novos = set(epicos_ids)
        return self._mudar_epicos(usuario_id, historia_id, lambda _atuais: novos)

    def vincular_epico(self, usuario_id: int, historia_id: int, epico_id: int) -> HistoriaDados:
        return self._mudar_epicos(usuario_id, historia_id, lambda atuais: atuais | {epico_id})

    def desvincular_epico(self, usuario_id: int, historia_id: int, epico_id: int) -> HistoriaDados:
        """Remove só o vínculo: a história e o épico continuam existindo."""
        return self._mudar_epicos(usuario_id, historia_id, lambda atuais: atuais - {epico_id})

    def _mudar_epicos(
        self, usuario_id: int, historia_id: int, novo_conjunto: Callable[[set[int]], set[int]]
    ) -> HistoriaDados:
        with self._sessao() as sessao:
            historia = self._acessivel(sessao, usuario_id, historia_id)
            atuais = epico_repository.ids_vinculados(sessao, historia.id)
            novos = set(novo_conjunto(set(atuais)))
            self._exigir_epicos_do_projeto(sessao, historia.projeto_id, novos - atuais)
            if novos != atuais:
                epico_repository.vincular(sessao, historia.id, novos - atuais)
                epico_repository.desvincular(sessao, historia.id, atuais - novos)
                self._auditar(
                    sessao, usuario_id, historia, "ALTERAR",
                    {"epicos": sorted(atuais)}, {"epicos": sorted(novos)},
                )
            return self._dados(sessao, [historia])[0]

    # ---------- excluir ----------

    def excluir(self, usuario_id: int, historia_id: int) -> InventarioHistoria:
        """Exclui a história com seus critérios e vínculos. Os épicos continuam existindo."""
        with self._sessao() as sessao:
            historia = self._acessivel(sessao, usuario_id, historia_id)
            epicos = epico_repository.ids_vinculados(sessao, historia.id)
            criterios = historia_repository.contar_criterios(sessao, [historia.id])[historia.id]
            anterior = {**_snapshot(historia, epicos), "criterios": criterios}
            self._auditar(sessao, usuario_id, historia, "EXCLUIR", anterior=anterior)
            historia_repository.excluir(sessao, historia)
            return InventarioHistoria(criterios=criterios, epicos=len(epicos))

    # ---------- internos ----------

    @staticmethod
    def _dados(sessao: Session, historias: list[Historia]) -> list[HistoriaDados]:
        ids = [h.id for h in historias]
        epicos = historia_repository.epicos_por_historia(sessao, ids)
        criterios = historia_repository.contar_criterios(sessao, ids)
        backlogs = historia_repository.backlogs_por_id(sessao, {h.backlog_id for h in historias})
        return [
            HistoriaDados(
                id=h.id,
                projeto_id=h.projeto_id,
                backlog_id=h.backlog_id,
                backlog_nome=backlogs[h.backlog_id][0],
                backlog_tipo=backlogs[h.backlog_id][1],
                codigo=h.codigo,
                papel=h.papel,
                acao=h.acao,
                beneficio=h.beneficio,
                story_points=h.story_points,
                moscow=h.moscow,
                epicos=tuple(EpicoRef(i, n) for i, n in epicos[h.id]),
                criterios_total=criterios[h.id],
            )
            for h in historias
        ]

    @staticmethod
    def _exigir_epicos_do_projeto(sessao: Session, projeto_id: int, epico_ids: set[int]) -> None:
        validos = epico_repository.validos_do_projeto(sessao, projeto_id, epico_ids)
        if epico_ids - validos:
            raise ErroDeValidacao({"epicos": "Épico inexistente ou de outro projeto."})

    @staticmethod
    def _auditar(sessao: Session, usuario_id: int, historia: Historia, operacao: str, anterior=None, posterior=None) -> None:
        auditoria_repository.registrar(
            sessao,
            usuario_id=usuario_id,
            entidade="historia",
            entidade_id=historia.id,
            operacao=operacao,
            valor_anterior=anterior,
            valor_posterior=posterior,
        )

    @staticmethod
    def _projeto(sessao: Session, usuario_id: int, projeto_id: int):
        projeto = projeto_repository.buscar_acessivel(sessao, usuario_id, projeto_id)
        if projeto is None:
            raise ProjetoNaoEncontrado()
        return projeto

    @staticmethod
    def _acessivel(sessao: Session, usuario_id: int, historia_id: int) -> Historia:
        historia = historia_repository.buscar_acessivel(sessao, usuario_id, historia_id)
        if historia is None:
            raise HistoriaNaoEncontrada()
        return historia
