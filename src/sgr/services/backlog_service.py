"""CRUD de backlogs (requisitos 5 e 6): um product backlog por projeto e vários sprint backlogs.

Regras:
- proprietário e membros do projeto gerenciam seus backlogs (o ator do storyboard é o
  "Product Owner / Membro da equipe"); quem não tem acesso ao projeto recebe "não encontrado";
- product backlog: no máximo um por projeto (checado aqui e pelo índice único do banco);
  só pode ser excluído quando está vazio;
- sprint backlog: nome, início e fim obrigatórios, fim posterior ao início, meta opcional;
  nasce PLANEJADO (a mudança de estado não faz parte do CRUD);
- excluir um sprint nunca apaga histórias: elas voltam ao product backlog com todos os dados;
- nome com até 120 caracteres; descrição/meta com até 280;
- toda escrita gera registro de auditoria.
"""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from sgr.db.session import get_session
from sgr.models import Backlog
from sgr.repositories import auditoria_repository, backlog_repository, projeto_repository
from sgr.services.auth_service import ErroDeValidacao
from sgr.services.projeto_service import ProjetoNaoEncontrado

NOME_MAX = 120
DESCRICAO_MAX = 280
NOME_PADRAO_PRODUCT = "Product Backlog"


@dataclass(frozen=True)
class BacklogDados:
    id: int
    projeto_id: int
    tipo: str  # "PRODUCT" ou "SPRINT"
    nome: str
    descricao: str | None
    data_inicio: date | None
    data_fim: date | None
    estado: str | None
    historias: int
    pontos: int

    @property
    def e_product(self) -> bool:
        return self.tipo == "PRODUCT"

    @property
    def duracao_dias(self) -> int | None:
        """Duração contando o dia inicial e o final (15/10 a 28/10 = 14 dias)."""
        if self.data_inicio and self.data_fim:
            return (self.data_fim - self.data_inicio).days + 1
        return None


@dataclass(frozen=True)
class HistoriaResumo:
    id: int
    codigo: str
    papel: str
    acao: str
    beneficio: str
    story_points: int | None
    moscow: str


@dataclass(frozen=True)
class BacklogsDoProjeto:
    product: BacklogDados | None
    sprints: list[BacklogDados]


class BacklogNaoEncontrado(Exception):
    def __init__(self) -> None:
        super().__init__("Backlog não encontrado.")


class ProductBacklogJaExiste(Exception):
    def __init__(self, nome: str) -> None:
        self.nome = nome
        super().__init__(
            f"Este projeto já tem o {nome}. Cada projeto admite apenas um product backlog; "
            "para outro, crie um novo projeto."
        )


class ProductBacklogComHistorias(Exception):
    def __init__(self, quantidade: int) -> None:
        self.quantidade = quantidade
        super().__init__(
            "Não é possível excluir o product backlog: "
            f"{quantidade} {'história depende' if quantidade == 1 else 'histórias dependem'} dele."
        )


class SemProductBacklog(Exception):
    def __init__(self) -> None:
        super().__init__(
            "Este sprint tem histórias e o projeto não tem product backlog para recebê-las. "
            "Crie o product backlog antes de excluir o sprint."
        )


def _como_data(valor: date | datetime | None) -> date | None:
    return valor.date() if isinstance(valor, datetime) else valor


def _texto(valor: str | None) -> str | None:
    return (valor or "").strip() or None


def _validar(
    nome: str | None,
    descricao: str | None,
    *,
    sprint: bool,
    inicio: date | None = None,
    fim: date | None = None,
) -> tuple[str, str | None, date | None, date | None]:
    nome = (nome or "").strip()
    descricao = _texto(descricao)
    inicio, fim = _como_data(inicio), _como_data(fim)
    erros: dict[str, str] = {}
    if not nome:
        erros["nome"] = "Informe o nome do backlog."
    elif len(nome) > NOME_MAX:
        erros["nome"] = f"O nome deve ter no máximo {NOME_MAX} caracteres."
    if descricao and len(descricao) > DESCRICAO_MAX:
        erros["descricao"] = f"O texto deve ter no máximo {DESCRICAO_MAX} caracteres."
    if sprint:
        if inicio is None:
            erros["data_inicio"] = "Informe a data de início."
        if fim is None:
            erros["data_fim"] = "Informe a data de fim."
        elif inicio is not None and fim <= inicio:
            erros["data_fim"] = "A data de fim deve ser posterior à data de início."
    if erros:
        raise ErroDeValidacao(erros)
    return nome, descricao, (inicio if sprint else None), (fim if sprint else None)


def _snapshot(b: Backlog) -> dict:
    return {
        "tipo": b.tipo,
        "nome": b.nome,
        "descricao": b.descricao,
        "data_inicio": b.data_inicio.isoformat() if b.data_inicio else None,
        "data_fim": b.data_fim.isoformat() if b.data_fim else None,
        "estado": b.estado,
    }


class BacklogService:
    def __init__(
        self, sessao: Callable[[], AbstractContextManager[Session]] = get_session
    ) -> None:
        self._sessao = sessao

    # ---------- leitura ----------

    def listar(self, usuario_id: int, projeto_id: int) -> BacklogsDoProjeto:
        with self._sessao() as sessao:
            self._projeto(sessao, usuario_id, projeto_id)
            product = backlog_repository.product_do_projeto(sessao, projeto_id)
            sprints = backlog_repository.sprints_do_projeto(sessao, projeto_id)
            todos = ([product] if product else []) + sprints
            contagens = backlog_repository.contagens(sessao, [b.id for b in todos])
            return BacklogsDoProjeto(
                product=self._dados(product, contagens) if product else None,
                sprints=[self._dados(s, contagens) for s in sprints],
            )

    def obter(self, usuario_id: int, backlog_id: int) -> BacklogDados:
        with self._sessao() as sessao:
            backlog = self._acessivel(sessao, usuario_id, backlog_id)
            return self._dados(backlog, backlog_repository.contagens(sessao, [backlog.id]))

    def listar_historias(self, usuario_id: int, backlog_id: int) -> list[HistoriaResumo]:
        with self._sessao() as sessao:
            backlog = self._acessivel(sessao, usuario_id, backlog_id)
            return [
                HistoriaResumo(h.id, h.codigo, h.papel, h.acao, h.beneficio, h.story_points, h.moscow)
                for h in backlog_repository.listar_historias(sessao, backlog.id)
            ]

    # ---------- criar ----------

    def criar_product(
        self, usuario_id: int, projeto_id: int, nome: str | None, descricao: str | None = None
    ) -> BacklogDados:
        nome, descricao, _, _ = _validar(nome, descricao, sprint=False)
        with self._sessao() as sessao:
            self._projeto(sessao, usuario_id, projeto_id)
            existente = backlog_repository.product_do_projeto(sessao, projeto_id)
            if existente:
                raise ProductBacklogJaExiste(existente.nome)
            try:
                # Savepoint: se duas requisições criarem ao mesmo tempo, o índice único
                # parcial do banco recusa a segunda.
                with sessao.begin_nested():
                    backlog = backlog_repository.criar_product(sessao, projeto_id, nome, descricao)
            except IntegrityError:
                existente = backlog_repository.product_do_projeto(sessao, projeto_id)
                raise ProductBacklogJaExiste(existente.nome if existente else nome) from None
            self._auditar(sessao, usuario_id, backlog, "CRIAR", posterior=_snapshot(backlog))
            return self._dados(backlog, {})

    def criar_sprint(
        self,
        usuario_id: int,
        projeto_id: int,
        nome: str | None,
        data_inicio: date | None,
        data_fim: date | None,
        meta: str | None = None,
    ) -> BacklogDados:
        nome, meta, inicio, fim = _validar(
            nome, meta, sprint=True, inicio=data_inicio, fim=data_fim
        )
        with self._sessao() as sessao:
            self._projeto(sessao, usuario_id, projeto_id)
            backlog = backlog_repository.criar_sprint(sessao, projeto_id, nome, meta, inicio, fim)
            self._auditar(sessao, usuario_id, backlog, "CRIAR", posterior=_snapshot(backlog))
            return self._dados(backlog, {})

    def sugerir_nome_sprint(self, usuario_id: int, projeto_id: int) -> str:
        with self._sessao() as sessao:
            self._projeto(sessao, usuario_id, projeto_id)
            return f"Sprint {backlog_repository.contar_sprints(sessao, projeto_id) + 1}"

    # ---------- atualizar ----------

    def atualizar(
        self,
        usuario_id: int,
        backlog_id: int,
        nome: str | None,
        descricao: str | None = None,
        data_inicio: date | None = None,
        data_fim: date | None = None,
    ) -> BacklogDados:
        """Altera os metadados. O estado do sprint e a quantidade de histórias não mudam."""
        with self._sessao() as sessao:
            backlog = self._acessivel(sessao, usuario_id, backlog_id)
            sprint = backlog.tipo == "SPRINT"
            nome, descricao, inicio, fim = _validar(
                nome, descricao, sprint=sprint, inicio=data_inicio, fim=data_fim
            )
            anterior = _snapshot(backlog)
            backlog.nome, backlog.descricao = nome, descricao
            if sprint:
                backlog.data_inicio, backlog.data_fim = inicio, fim
            posterior = _snapshot(backlog)
            if posterior != anterior:
                sessao.flush()
                self._auditar(
                    sessao, usuario_id, backlog, "ALTERAR", anterior=anterior, posterior=posterior
                )
            return self._dados(backlog, backlog_repository.contagens(sessao, [backlog.id]))

    # ---------- excluir ----------

    def excluir(self, usuario_id: int, backlog_id: int) -> int:
        """Exclui o backlog. Devolve quantas histórias voltaram ao product backlog (só sprint)."""
        with self._sessao() as sessao:
            backlog = self._acessivel(sessao, usuario_id, backlog_id)
            qtd, _ = backlog_repository.contagens(sessao, [backlog.id])[backlog.id]
            anterior = {**_snapshot(backlog), "historias": qtd}
            devolvidas: list[int] = []

            if backlog.tipo == "PRODUCT":
                if qtd:
                    raise ProductBacklogComHistorias(qtd)
            elif qtd:
                product = backlog_repository.product_do_projeto(sessao, backlog.projeto_id)
                if product is None:
                    raise SemProductBacklog()
                devolvidas = backlog_repository.devolver_historias(sessao, backlog.id, product.id)
                for historia_id in devolvidas:
                    auditoria_repository.registrar(
                        sessao,
                        usuario_id=usuario_id,
                        entidade="historia",
                        entidade_id=historia_id,
                        operacao="ALTERAR",
                        valor_anterior={"backlog_id": backlog.id},
                        valor_posterior={"backlog_id": product.id},
                    )

            backlog_repository.excluir(sessao, backlog)
            auditoria_repository.registrar(
                sessao,
                usuario_id=usuario_id,
                entidade="backlog",
                entidade_id=backlog_id,
                operacao="EXCLUIR",
                valor_anterior=anterior,
            )
            return len(devolvidas)

    # ---------- internos ----------

    @staticmethod
    def _dados(backlog: Backlog, contagens: dict[int, tuple[int, int]]) -> BacklogDados:
        historias, pontos = contagens.get(backlog.id, (0, 0))
        return BacklogDados(
            id=backlog.id,
            projeto_id=backlog.projeto_id,
            tipo=backlog.tipo,
            nome=backlog.nome,
            descricao=backlog.descricao,
            data_inicio=backlog.data_inicio,
            data_fim=backlog.data_fim,
            estado=backlog.estado,
            historias=historias,
            pontos=pontos,
        )

    @staticmethod
    def _auditar(sessao: Session, usuario_id: int, backlog: Backlog, operacao: str, **valores) -> None:
        auditoria_repository.registrar(
            sessao,
            usuario_id=usuario_id,
            entidade="backlog",
            entidade_id=backlog.id,
            operacao=operacao,
            valor_anterior=valores.get("anterior"),
            valor_posterior=valores.get("posterior"),
        )

    @staticmethod
    def _projeto(sessao: Session, usuario_id: int, projeto_id: int):
        projeto = projeto_repository.buscar_acessivel(sessao, usuario_id, projeto_id)
        if projeto is None:
            raise ProjetoNaoEncontrado()
        return projeto

    @staticmethod
    def _acessivel(sessao: Session, usuario_id: int, backlog_id: int) -> Backlog:
        backlog = backlog_repository.buscar_acessivel(sessao, usuario_id, backlog_id)
        if backlog is None:
            raise BacklogNaoEncontrado()
        return backlog
