from typing import Any
from pydantic import BaseModel, Field

class ErrorContent(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str

class ErrorResponse(BaseModel):
    error: ErrorContent

