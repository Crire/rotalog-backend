"""Erros da aplicação e seu contrato de saída."""

from typing import Any

from pydantic import BaseModel, Field


class RotaLogError(Exception):
    """Erro esperado e seguro para exposição pela API."""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class ErrorContent(BaseModel):
    """Conteúdo padronizado de um erro HTTP."""

    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str


class ErrorResponse(BaseModel):
    """Envelope canônico de erro da API."""

    error: ErrorContent
