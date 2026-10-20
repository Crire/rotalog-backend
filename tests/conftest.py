"""Banco temporário isolado por schema; nunca remove o schema public."""

import os
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from rotalog.core.config import Environment, Settings

# Configuração explícita do bootstrap de teste; não abre conexão.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")
os.environ.setdefault(
    "ROTALOG_DATABASE_URL", "postgresql+psycopg://localhost/rotalog_test"
)


@pytest.fixture
def database_url() -> Iterator[str]:
    raw_url = os.getenv("ROTALOG_TEST_DATABASE_URL")
    if not raw_url:
        if os.getenv("CI"):
            pytest.fail("CI deve fornecer ROTALOG_TEST_DATABASE_URL para testes reais")
        pytest.skip("ROTALOG_TEST_DATABASE_URL não configurada")
    url = make_url(raw_url)
    if url.drivername != "postgresql+psycopg" or "test" not in (url.database or ""):
        pytest.fail("Use um PostgreSQL dedicado com 'test' no nome do banco")
    schema = f"test_{uuid4().hex}"
    engine = create_engine(url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        yield url.update_query_dict(
            {"options": f"-csearch_path={schema}"}
        ).render_as_string(
            hide_password=False,
        )
    finally:
        with engine.connect() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()


@pytest.fixture
def alembic_config(database_url: str) -> Config:
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


@pytest.fixture
def demo_settings(database_url: str) -> Settings:
    return Settings(
        _env_file=None,
        database_url=database_url,
        environment=Environment.TEST,
        demo_enabled=True,
        jwt_secret="test-only-jwt-secret-with-at-least-32-bytes",
        cors_origins=["http://localhost:5173"],
    )


@pytest.fixture
def demo_client(
    alembic_config: Config, demo_settings: Settings
) -> Iterator[TestClient]:
    from rotalog.api.main import create_app
    from rotalog.demo.seed import seed_demo

    command.upgrade(alembic_config, "head")
    app = create_app(demo_settings)
    seed_demo(app.state.session_factory, demo_settings, "synthetic-test-password")
    with TestClient(app) as client:
        yield client
