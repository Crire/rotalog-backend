from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Request, Response
from starlette.concurrency import run_in_threadpool

from rotalog.identity.dependencies import (
    ApplicationSettings,
    CurrentUser,
    SessionFactory,
)
from rotalog.operations import file_service
from rotalog.operations.file_schemas import (
    DownloadAccess,
    FileStatus,
    UploadIntent,
    UploadIntentResponse,
)
from rotalog.operations.file_transport import receive_limited_body

router = APIRouter(tags=["arquivos privados da demo"])
Key = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=200)]
DownloadToken = Annotated[
    str, Header(alias="X-Download-Token", min_length=40, max_length=100)
]


@router.post(
    "/files/upload-intents", status_code=201, response_model=UploadIntentResponse
)
def intent(
    data: UploadIntent,
    key: Key,
    actor: CurrentUser,
    factory: SessionFactory,
    settings: ApplicationSettings,
):
    return file_service.create_intent(data, key, actor, factory, settings)


@router.put(
    "/files/{file_id}/content",
    status_code=204,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/octet-stream": {
                    "schema": {"type": "string", "format": "binary"}
                }
            },
        }
    },
)
async def content(
    file_id: UUID,
    request: Request,
    key: Key,
    actor: CurrentUser,
    factory: SessionFactory,
    settings: ApplicationSettings,
):
    data = await receive_limited_body(request, settings.product_image_max_bytes)
    await run_in_threadpool(
        file_service.upload_content, file_id, data, key, actor, factory, settings
    )
    return Response(status_code=204)


@router.post(
    "/files/{file_id}/confirm-upload", status_code=202, response_model=FileStatus
)
def confirm(
    file_id: UUID,
    key: Key,
    actor: CurrentUser,
    factory: SessionFactory,
    settings: ApplicationSettings,
):
    return file_service.confirm_upload(file_id, key, actor, factory, settings)


@router.get("/files/{file_id}", response_model=FileStatus)
def status(file_id: UUID, actor: CurrentUser, factory: SessionFactory):
    return file_service.get_status(file_id, actor, factory)


@router.get("/files/{file_id}/download-access", response_model=DownloadAccess)
def download_access(
    file_id: UUID, actor: CurrentUser, factory: SessionFactory, response: Response
):
    response.headers["Cache-Control"] = "no-store"
    return file_service.download_access(file_id, actor, factory)


@router.get(
    "/files/{file_id}/content",
    response_class=Response,
    responses={200: {"content": {"image/png": {}, "image/jpeg": {}}}},
)
def download(
    file_id: UUID,
    token: DownloadToken,
    actor: CurrentUser,
    factory: SessionFactory,
    settings: ApplicationSettings,
):
    data, mime = file_service.read_content(
        file_id, actor, factory, settings, grant_token=token
    )
    return Response(
        data,
        media_type=mime,
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f'inline; filename="{file_id}"',
        },
    )
