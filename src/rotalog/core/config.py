"""Configuração da aplicação carregada a partir do ambiente."""

from enum import StrEnum
from functools import lru_cache

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


class Environment(StrEnum):
    """Ambientes reconhecidos pela aplicação."""

    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Configurações validadas provenientes de variáveis ``ROTALOG_*``."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="ROTALOG_",
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
    )

    app_name: str = "RotaLog API"
    app_description: str = "API backend do marketplace B2B RotaLog."
    app_version: str = "0.1.0"
    environment: Environment = Environment.DEVELOPMENT
    debug: bool = False
    database_url: SecretStr
    demo_enabled: bool = False
    jwt_secret: SecretStr | None = None

    @field_validator("jwt_secret", mode="before")
    @classmethod
    def empty_jwt_secret(cls, value: str | SecretStr | None) -> str | SecretStr | None:
        return None if value == "" else value

    @field_validator("jwt_secret")
    @classmethod
    def validate_jwt_secret(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and len(value.get_secret_value().encode()) < 32:
            raise ValueError("ROTALOG_JWT_SECRET deve ter pelo menos 32 bytes")
        return value

    @model_validator(mode="after")
    def validate_demo_environment(self) -> "Settings":
        if self.demo_enabled and self.environment not in {
            Environment.DEVELOPMENT,
            Environment.TEST,
        }:
            raise ValueError("A demo só pode ser habilitada em development ou test")
        if self.demo_enabled and self.jwt_secret is None:
            raise ValueError("ROTALOG_JWT_SECRET é obrigatória para habilitar a demo")
        return self

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr) -> SecretStr:
        """Aceita somente a conexão síncrona PostgreSQL/psycopg da baseline."""

        raw_url = value.get_secret_value()
        try:
            driver_name = make_url(raw_url).drivername
        except ArgumentError as exc:
            raise ValueError("ROTALOG_DATABASE_URL inválida") from exc

        if driver_name != "postgresql+psycopg":
            raise ValueError(
                "ROTALOG_DATABASE_URL deve usar o driver postgresql+psycopg"
            )
        return value


@lru_cache
def get_settings() -> Settings:
    """Retorna uma única instância imutável das configurações."""

    return Settings()
