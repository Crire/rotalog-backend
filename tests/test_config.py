"""Testes das configurações carregadas do ambiente."""

import pytest
from pydantic import ValidationError
from pytest import MonkeyPatch

from rotalog.core.config import Environment, Settings


def test_settings_reads_prefixed_environment_variables(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("ROTALOG_ENVIRONMENT", "test")
    monkeypatch.setenv("ROTALOG_DEBUG", "true")
    monkeypatch.setenv("ROTALOG_APP_NAME", "RotaLog Environment API")
    monkeypatch.setenv(
        "ROTALOG_DATABASE_URL",
        "postgresql+psycopg://localhost/rotalog_test",
    )

    settings = Settings(_env_file=None)

    assert settings.environment is Environment.TEST
    assert settings.debug is True
    assert settings.app_name == "RotaLog Environment API"


def test_database_url_is_required(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("ROTALOG_DATABASE_URL", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_database_url_requires_synchronous_psycopg() -> None:
    with pytest.raises(ValidationError, match="postgresql\\+psycopg"):
        Settings(_env_file=None, database_url="sqlite+pysqlite:///:memory:")


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_demo_is_blocked_outside_local_and_test(environment: str) -> None:
    with pytest.raises(ValidationError, match="development ou test"):
        Settings(
            _env_file=None,
            environment=environment,
            demo_enabled=True,
            database_url="postgresql+psycopg://localhost/rotalog_test",
            jwt_secret="synthetic-key-for-tests-with-more-than-32-bytes",
        )


def test_demo_requires_signing_key(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("ROTALOG_JWT_SECRET", raising=False)
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(
            _env_file=None,
            environment="test",
            demo_enabled=True,
            database_url="postgresql+psycopg://localhost/rotalog_test",
        )
