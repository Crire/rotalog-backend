"""Tipos comuns de entrada, paginação e conflitos versionados."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from rotalog.core.errors import RotaLogError

Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
Reason = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=5, max_length=500)
]
Quantity = Annotated[int, Field(strict=True, ge=0, le=2_147_483_647)]
PositiveQuantity = Annotated[int, Field(strict=True, ge=1, le=2_147_483_647)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Versioned(Input):
    expected_version: Annotated[int, Field(strict=True, ge=1)]


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int
    is_synthetic: Literal[True] = True
    label: str = "SIMULAÇÃO — dados sintéticos"


def fail(code: str, message: str, status: int = 409) -> None:
    raise RotaLogError(code=code, message=message, status_code=status)


def check_version(actual: int, expected: int) -> None:
    if actual != expected:
        fail("VERSION_CONFLICT", "Versão desatualizada; consulte o recurso novamente.")
