"""Contratos de upload privado da demo e consulta sem paths físicos."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from rotalog.core.contracts import Input


class UploadIntent(Input):
    purpose: Literal["PRODUCT_IMAGE"]
    product_id: UUID
    size_bytes: Annotated[int, Field(strict=True, gt=0, le=8388608)]
    mime_type: Literal["image/png", "image/jpeg"]
    sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class FileStatus(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    file_id: UUID
    purpose: Literal["PRODUCT_IMAGE"]
    product_id: UUID
    status: str
    size_bytes: int
    mime_type: str
    sha256: str
    expires_at: datetime
    rejection_reason: str | None
    is_synthetic: Literal[True] = True
    scan_mode: Literal["SYNTHETIC_IMAGE_VALIDATION_ONLY"] = (
        "SYNTHETIC_IMAGE_VALIDATION_ONLY"
    )


class UploadIntentResponse(FileStatus):
    upload_url: str
    method: Literal["PUT"] = "PUT"
    headers: dict[str, str]
    requires_authentication: Literal[True] = True
    max_bytes: int
    max_pixels: int


class DownloadAccess(BaseModel):
    file_id: UUID
    download_url: str
    method: Literal["GET"] = "GET"
    headers: dict[str, str]
    expires_at: datetime
    requires_authentication: Literal[True] = True
