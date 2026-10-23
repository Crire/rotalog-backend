from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Response

from rotalog.catalog import image_service
from rotalog.catalog.image_schemas import (
    ProductGallery,
    ProductImageAttach,
    ProductImageOrder,
)
from rotalog.core.contracts import Versioned
from rotalog.identity.dependencies import (
    ApplicationSettings,
    CurrentUser,
    SessionFactory,
)

router = APIRouter(tags=["imagens de produtos"])
Key = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=200)]


@router.get("/products/{product_id}/images", response_model=ProductGallery)
def gallery(product_id: UUID, actor: CurrentUser, factory: SessionFactory):
    return image_service.get_gallery(product_id, actor, factory)


@router.post(
    "/admin/products/{product_id}/images",
    status_code=201,
    response_model=ProductGallery,
)
def attach(
    product_id: UUID,
    data: ProductImageAttach,
    key: Key,
    actor: CurrentUser,
    factory: SessionFactory,
    settings: ApplicationSettings,
):
    return image_service.gallery_command(
        product_id, "attach", data, key, actor, factory, settings
    )


@router.post(
    "/admin/products/{product_id}/images/reorder", response_model=ProductGallery
)
def reorder(
    product_id: UUID,
    data: ProductImageOrder,
    key: Key,
    actor: CurrentUser,
    factory: SessionFactory,
    settings: ApplicationSettings,
):
    return image_service.gallery_command(
        product_id, "reorder", data, key, actor, factory, settings
    )


@router.post(
    "/admin/products/{product_id}/images/{image_id}/set-primary",
    response_model=ProductGallery,
)
def primary(
    product_id: UUID,
    image_id: UUID,
    data: Versioned,
    key: Key,
    actor: CurrentUser,
    factory: SessionFactory,
    settings: ApplicationSettings,
):
    return image_service.gallery_command(
        product_id,
        "set-primary",
        data,
        key,
        actor,
        factory,
        settings,
        image_id=image_id,
    )


@router.delete(
    "/admin/products/{product_id}/images/{image_id}", response_model=ProductGallery
)
def remove(
    product_id: UUID,
    image_id: UUID,
    data: Versioned,
    key: Key,
    actor: CurrentUser,
    factory: SessionFactory,
    settings: ApplicationSettings,
):
    return image_service.gallery_command(
        product_id, "remove", data, key, actor, factory, settings, image_id=image_id
    )


@router.get(
    "/products/{product_id}/images/{image_id}/content",
    response_class=Response,
    responses={200: {"content": {"image/png": {}, "image/jpeg": {}}}},
)
def content(
    product_id: UUID,
    image_id: UUID,
    actor: CurrentUser,
    factory: SessionFactory,
    settings: ApplicationSettings,
):
    data, mime = image_service.image_content(
        product_id, image_id, actor, factory, settings
    )
    return Response(
        data,
        media_type=mime,
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f'inline; filename="{image_id}"',
        },
    )
