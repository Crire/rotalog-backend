"""Ambiente Alembic da aplicação RotaLog."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.engine import Connection, create_engine

import rotalog.core.models  # noqa: F401
from rotalog.core.config import get_settings
from rotalog.core.database import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _database_url() -> str:
    configured_url = config.get_main_option("sqlalchemy.url")
    if configured_url:
        return configured_url
    return get_settings().database_url.get_secret_value()


def run_migrations_offline() -> None:
    """Executa migrações sem criar uma conexão."""

    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def _extension_relation_names(connection: Connection) -> set[str]:
    """Retorna relações pertencentes a extensões, não ao esquema da aplicação."""

    return set(
        connection.execute(
            text(
                """
                SELECT c.relname
                FROM pg_depend dependency
                JOIN pg_extension extension ON extension.oid = dependency.refobjid
                JOIN pg_class c ON c.oid = dependency.objid
                WHERE c.relkind IN ('r', 'v', 'm', 'S')
                """
            )
        ).scalars()
    )


def _run_migrations(connection: Connection) -> None:
    extension_relations = _extension_relation_names(connection)
    # A consulta de metadados abre uma transação implícita no SQLAlchemy. Ela
    # precisa terminar antes de o Alembic iniciar a própria transação de DDL.
    connection.commit()
    configured_schema = config.get_main_option("version_table_schema")
    version_table_schema = configured_schema or connection.scalar(
        text("SELECT current_schema()")
    )
    version_table = config.get_main_option("version_table") or "alembic_version"

    def include_object(
        _object: object,
        name: str | None,
        object_type: str,
        reflected: bool,
        _compare_to: object | None,
    ) -> bool:
        """Impede que tabelas auxiliares do PostGIS virem migrações da aplicação."""

        if not reflected or object_type != "table" or name is None:
            return True

        # A tabela de versão é infraestrutura do Alembic, não um modelo da
        # aplicação. Ao usar um schema de teste ela precisa ser explicitamente
        # excluída da comparação de metadados.
        if name == version_table:
            return False

        return name not in extension_relations

    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        include_object=include_object,
        version_table_schema=version_table_schema,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Executa migrações em uma conexão PostgreSQL síncrona."""

    connectable = create_engine(_database_url(), poolclass=pool.NullPool)
    try:
        with connectable.connect() as connection:
            _run_migrations(connection)
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
