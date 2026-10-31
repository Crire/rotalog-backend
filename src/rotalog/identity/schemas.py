"""Schemas de entrada e saída do módulo de identidade."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    StringConstraints,
    field_validator,
)

from rotalog.identity.models import Role

NonBlankName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]


class RegisterRequest(BaseModel):
    """Autocadastro exclusivo da demo: uma nova conta com organização própria."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(
        min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$"
    )
    password: SecretStr = Field(min_length=12, max_length=1024)
    name: NonBlankName
    organization_name: NonBlankName
    role: Literal["BUYER_ADMIN", "SUPPLIER_OPERATOR"]

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("email")
    @classmethod
    def require_synthetic_email(cls, value: str) -> str:
        if not value.endswith(".invalid"):
            raise ValueError("Use um email sintético com domínio terminado em .invalid")
        return value


class DriverProvisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(
        min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$"
    )
    password: SecretStr = Field(min_length=12, max_length=1024)
    name: NonBlankName

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("email")
    @classmethod
    def require_synthetic_email(cls, value: str) -> str:
        if not value.endswith(".invalid"):
            raise ValueError("Use um email sintético com domínio terminado em .invalid")
        return value


class OrganizationAccess(BaseModel):
    id: UUID
    name: str
    role: Role


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    name: str
    role: Role
    organization_id: UUID
    organizations: list[OrganizationAccess] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    demo_run_id: UUID
    session_id: UUID | None = Field(default=None, exclude=True)
    auth_version: int = Field(default=1, exclude=True)
    is_synthetic: Literal[True] = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = 600
    refresh_token: str | None = None
    csrf_token: str | None = None
    user: UserResponse


class RefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    refresh_token: SecretStr | None = Field(default=None, min_length=32, max_length=256)


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: SecretStr = Field(min_length=1, max_length=1024)
    new_password: SecretStr = Field(min_length=12, max_length=1024)


class SessionResponse(BaseModel):
    id: UUID
    client_type: Literal["native", "browser"]
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    current: bool
