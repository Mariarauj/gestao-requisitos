"""Base declarativa com convenção de nomes para constraints e índices.

A convenção garante nomes previsíveis (pk_*, fk_*, uq_*, ck_*, ix_*), os mesmos
usados nas migrations do Alembic e no documento do projeto físico do banco.
"""
from sqlalchemy import BigInteger, MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    # Ids e chaves estrangeiras são BIGINT/BIGSERIAL (ver convenções do projeto físico).
    type_annotation_map = {int: BigInteger}
