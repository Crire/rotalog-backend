"""Schemas de entrada e saída do módulo de identidade."""

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
    role: Literal["comprador", "fornecedor"]

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


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    name: str
    role: Role
    organization_id: UUID
    demo_run_id: UUID
    is_synthetic: Literal[True] = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = 900
    user: UserResponse
