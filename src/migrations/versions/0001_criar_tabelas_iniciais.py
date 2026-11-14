"""Cria as nove tabelas do projeto físico do banco (artefato 7).

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

NOW = sa.text("now()")


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
    ]


def upgrade() -> None:
    # 5.1 usuario
    op.create_table(
        "usuario",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("nome", sa.String(120), nullable=False),
        sa.Column("email", sa.String(160), nullable=False),
        sa.Column("senha_hash", sa.String(60), nullable=False),
        sa.Column("ativo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_usuario")),
        sa.UniqueConstraint("email", name=op.f("uq_usuario_email")),
    )

    # 5.2 projeto
    op.create_table(
        "projeto",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("nome", sa.String(120), nullable=False),
        sa.Column("descricao", sa.String(280), nullable=True),
        sa.Column("proprietario_id", sa.BigInteger(), nullable=False),
        sa.Column("arquivado", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_projeto")),
        sa.ForeignKeyConstraint(
            ["proprietario_id"], ["usuario.id"],
            name=op.f("fk_projeto_proprietario_id_usuario"), ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("proprietario_id", "nome", name=op.f("uq_projeto_proprietario_id_nome")),
    )

    # 5.3 projeto_membro
    op.create_table(
        "projeto_membro",
        sa.Column("projeto_id", sa.BigInteger(), nullable=False),
        sa.Column("usuario_id", sa.BigInteger(), nullable=False),
        sa.Column("entrou_em", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("projeto_id", "usuario_id", name=op.f("pk_projeto_membro")),
        sa.ForeignKeyConstraint(
            ["projeto_id"], ["projeto.id"],
            name=op.f("fk_projeto_membro_projeto_id_projeto"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"], ["usuario.id"],
            name=op.f("fk_projeto_membro_usuario_id_usuario"), ondelete="CASCADE",
        ),
    )

    # 5.4 backlog (product e sprint em tabela única, com discriminador)
    op.create_table(
        "backlog",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("projeto_id", sa.BigInteger(), nullable=False),
        sa.Column("tipo", sa.String(8), nullable=False),
        sa.Column("nome", sa.String(120), nullable=False),
        sa.Column("descricao", sa.String(280), nullable=True),
        sa.Column("data_inicio", sa.Date(), nullable=True),
        sa.Column("data_fim", sa.Date(), nullable=True),
        sa.Column("estado", sa.String(12), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_backlog")),
        sa.ForeignKeyConstraint(
            ["projeto_id"], ["projeto.id"],
            name=op.f("fk_backlog_projeto_id_projeto"), ondelete="CASCADE",
        ),
        sa.CheckConstraint("tipo IN ('PRODUCT', 'SPRINT')", name=op.f("ck_backlog_tipo")),
        sa.CheckConstraint(
            "estado IN ('PLANEJADO', 'EM_ANDAMENTO', 'ENCERRADO')", name=op.f("ck_backlog_estado")
        ),
        sa.CheckConstraint(
            "(tipo = 'PRODUCT' AND data_inicio IS NULL AND data_fim IS NULL AND estado IS NULL) "
            "OR (tipo = 'SPRINT' AND data_inicio IS NOT NULL AND data_fim IS NOT NULL "
            "AND estado IS NOT NULL)",
            name=op.f("ck_backlog_tipo_atributos"),
        ),
        sa.CheckConstraint(
            "tipo <> 'SPRINT' OR data_fim > data_inicio", name=op.f("ck_backlog_periodo")
        ),
    )
    op.create_index(
        "ux_backlog_product_por_projeto", "backlog", ["projeto_id"],
        unique=True, postgresql_where=sa.text("tipo = 'PRODUCT'"),
    )
    op.create_index("ix_backlog_projeto_tipo", "backlog", ["projeto_id", "tipo"])

    # 5.5 historia
    op.create_table(
        "historia",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("projeto_id", sa.BigInteger(), nullable=False),
        sa.Column("backlog_id", sa.BigInteger(), nullable=False),
        sa.Column("codigo", sa.String(12), nullable=False),
        sa.Column("papel", sa.String(120), nullable=False),
        sa.Column("acao", sa.String(200), nullable=False),
        sa.Column("beneficio", sa.String(200), nullable=False),
        sa.Column("story_points", sa.SmallInteger(), nullable=True),
        sa.Column("moscow", sa.CHAR(1), nullable=False),
        sa.Column("rice_reach", sa.Integer(), nullable=True),
        sa.Column("rice_impact", sa.Numeric(4, 2), nullable=True),
        sa.Column("rice_confidence", sa.SmallInteger(), nullable=True),
        sa.Column("rice_effort", sa.SmallInteger(), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_historia")),
        sa.ForeignKeyConstraint(
            ["projeto_id"], ["projeto.id"],
            name=op.f("fk_historia_projeto_id_projeto"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["backlog_id"], ["backlog.id"],
            name=op.f("fk_historia_backlog_id_backlog"), ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("projeto_id", "codigo", name=op.f("uq_historia_projeto_id_codigo")),
        sa.CheckConstraint(
            "story_points IN (0, 1, 2, 3, 5, 8, 13, 21, 34, 55)",
            name=op.f("ck_historia_story_points"),
        ),
        sa.CheckConstraint("moscow IN ('M', 'S', 'C', 'W')", name=op.f("ck_historia_moscow")),
        sa.CheckConstraint("rice_reach >= 0", name=op.f("ck_historia_rice_reach")),
        sa.CheckConstraint(
            "rice_impact IN (3, 2, 1, 0.5, 0.25)", name=op.f("ck_historia_rice_impact")
        ),
        sa.CheckConstraint(
            "rice_confidence IN (100, 80, 50)", name=op.f("ck_historia_rice_confidence")
        ),
        sa.CheckConstraint(
            "rice_effort IN (1, 2, 3, 5, 8, 13, 21, 34, 55)", name=op.f("ck_historia_rice_effort")
        ),
        sa.CheckConstraint(
            "(rice_reach IS NULL AND rice_impact IS NULL AND rice_confidence IS NULL "
            "AND rice_effort IS NULL) OR (rice_reach IS NOT NULL AND rice_impact IS NOT NULL "
            "AND rice_confidence IS NOT NULL AND rice_effort IS NOT NULL)",
            name=op.f("ck_historia_rice_completo"),
        ),
    )
    op.create_index("ix_historia_backlog", "historia", ["backlog_id"])
    op.create_index("ix_historia_projeto", "historia", ["projeto_id"])
    op.create_index(
        "ix_historia_backlog_rice", "historia",
        ["backlog_id", "rice_reach", "rice_impact", "rice_confidence", "rice_effort"],
    )

    # 5.6 criterio_aceitacao
    op.create_table(
        "criterio_aceitacao",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("historia_id", sa.BigInteger(), nullable=False),
        sa.Column("contexto", sa.Text(), nullable=False),
        sa.Column("acao", sa.Text(), nullable=False),
        sa.Column("resultado", sa.Text(), nullable=False),
        sa.Column("ordem", sa.SmallInteger(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_criterio_aceitacao")),
        sa.ForeignKeyConstraint(
            ["historia_id"], ["historia.id"],
            name=op.f("fk_criterio_aceitacao_historia_id_historia"), ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "historia_id", "ordem", name=op.f("uq_criterio_aceitacao_historia_id_ordem")
        ),
    )
    op.create_index("ix_criterio_historia", "criterio_aceitacao", ["historia_id", "ordem"])

    # 5.7 epico
    op.create_table(
        "epico",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("projeto_id", sa.BigInteger(), nullable=False),
        sa.Column("nome", sa.String(120), nullable=False),
        sa.Column("descricao", sa.String(280), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_epico")),
        sa.ForeignKeyConstraint(
            ["projeto_id"], ["projeto.id"],
            name=op.f("fk_epico_projeto_id_projeto"), ondelete="CASCADE",
        ),
        sa.UniqueConstraint("projeto_id", "nome", name=op.f("uq_epico_projeto_id_nome")),
    )
    op.create_index("ix_epico_projeto", "epico", ["projeto_id"])

    # 5.8 epico_historia
    op.create_table(
        "epico_historia",
        sa.Column("epico_id", sa.BigInteger(), nullable=False),
        sa.Column("historia_id", sa.BigInteger(), nullable=False),
        sa.Column("vinculado_em", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("epico_id", "historia_id", name=op.f("pk_epico_historia")),
        sa.ForeignKeyConstraint(
            ["epico_id"], ["epico.id"],
            name=op.f("fk_epico_historia_epico_id_epico"), ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["historia_id"], ["historia.id"],
            name=op.f("fk_epico_historia_historia_id_historia"), ondelete="CASCADE",
        ),
    )
    op.create_index("ix_epico_historia_historia", "epico_historia", ["historia_id"])

    # 5.9 registro_auditoria
    op.create_table(
        "registro_auditoria",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("usuario_id", sa.BigInteger(), nullable=True),
        sa.Column("entidade", sa.String(30), nullable=False),
        sa.Column("entidade_id", sa.BigInteger(), nullable=False),
        sa.Column("operacao", sa.String(8), nullable=False),
        sa.Column("valor_anterior", postgresql.JSONB(), nullable=True),
        sa.Column("valor_posterior", postgresql.JSONB(), nullable=True),
        sa.Column("ocorrido_em", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_registro_auditoria")),
        sa.ForeignKeyConstraint(
            ["usuario_id"], ["usuario.id"],
            name=op.f("fk_registro_auditoria_usuario_id_usuario"), ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "entidade IN ('projeto', 'backlog', 'historia', 'criterio_aceitacao', 'epico', 'usuario')",
            name=op.f("ck_registro_auditoria_entidade"),
        ),
        sa.CheckConstraint(
            "operacao IN ('CRIAR', 'ALTERAR', 'EXCLUIR')", name=op.f("ck_registro_auditoria_operacao")
        ),
    )
    op.create_index(
        "ix_auditoria_entidade", "registro_auditoria", ["entidade", "entidade_id", "ocorrido_em"]
    )
    op.create_index("ix_auditoria_usuario", "registro_auditoria", ["usuario_id", "ocorrido_em"])


def downgrade() -> None:
    for tabela in (
        "registro_auditoria",
        "epico_historia",
        "epico",
        "criterio_aceitacao",
        "historia",
        "backlog",
        "projeto_membro",
        "projeto",
        "usuario",
    ):
        op.drop_table(tabela)
