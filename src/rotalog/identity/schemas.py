"""Schemas de entrada e saída do módulo de identidade."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from rotalog.identity.models import Role


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
