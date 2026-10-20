from uuid import UUID

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session, sessionmaker

from rotalog.catalog.models import Offer, OfferPriceVersion, Product
from rotalog.catalog.schemas import (
    OfferCreate,
    OfferFilters,
    OfferResponse,
    PriceChange,
    ProductCreate,
    ProductResponse,
)
from rotalog.core.contracts import Page, check_version, fail
from rotalog.core.database import transactional_session
from rotalog.core.money import decimal_string, minor
from rotalog.identity.models import Role
from rotalog.identity.schemas import UserResponse
from rotalog.identity.service import authorize
from rotalog.inventory.models import CapacitySlot, InventoryProjection, Warehouse
from rotalog.inventory.service import initialize_projection, owned_warehouse
from rotalog.organizations.models import Organization


def create_product(
    data: ProductCreate, actor: UserResponse, factory: sessionmaker[Session]
) -> ProductResponse:
    with transactional_session(factory) as session:
        authorize(session, actor, {Role.ADMIN}, write=True)
        item = Product(**data.model_dump(), demo_run_id=actor.demo_run_id)
        session.add(item)
        session.flush()
        return ProductResponse.model_validate(item)


def publish_product(
    product_id: UUID,
    expected_version: int,
    actor: UserResponse,
    factory: sessionmaker[Session],
) -> ProductResponse:
    with transactional_session(factory) as session:
        authorize(session, actor, {Role.ADMIN}, write=True)
        item = session.scalar(
            select(Product)
            .where(Product.id == product_id, Product.demo_run_id == actor.demo_run_id)
            .with_for_update()
        )
        if item is None:
            fail("PRODUCT_NOT_FOUND", "Produto não encontrado.", 404)
        check_version(item.version, expected_version)
        required = (
            item.brand,
            item.category,
            item.net_content,
            item.net_content_unit,
            item.packaging_type,
            item.packaging_quantity,
            item.gross_weight_grams,
            item.volume_cm3,
        )
        if not all(required):
            fail(
                "PRODUCT_INCOMPLETE",
                "Variante histórica incompleta; complete os dados antes de publicar.",
                422,
            )
        item.publication_state = "PUBLISHED"
        item.version += 1
        session.flush()
        return ProductResponse.model_validate(item)


def list_products(
    actor: UserResponse,
    factory: sessionmaker[Session],
    page: int,
    page_size: int,
    search: str | None = None,
    product_id: UUID | None = None,
):
    with transactional_session(factory) as session:
        authorize(session, actor)
        query = select(Product).where(
            Product.demo_run_id == actor.demo_run_id,
            Product.publication_state == "PUBLISHED",
        )
        if search:
            query = query.where(Product.name.icontains(search, autoescape=True))
        if product_id:
            item = session.scalar(query.where(Product.id == product_id))
            if item is None:
                fail("PRODUCT_NOT_FOUND", "Produto não encontrado.", 404)
            return ProductResponse.model_validate(item)
        total = session.scalar(select(func.count()).select_from(query.subquery()))
        return Page(
            items=[
                ProductResponse.model_validate(item)
                for item in session.scalars(
                    query.order_by(Product.name, Product.id)
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ],
            total=total,
            page=page,
            page_size=page_size,
        )


def offer_response(session: Session, item: Offer) -> OfferResponse:
    product = session.get(Product, item.product_id)
    supplier = session.get(Organization, item.supplier_organization_id)
    warehouse = session.get(Warehouse, item.warehouse_id)
    balance = session.scalar(
        select(InventoryProjection).where(
            InventoryProjection.offer_id == item.id,
            InventoryProjection.warehouse_id == item.warehouse_id,
        )
    )
    return OfferResponse(
        id=item.id,
        product_id=item.product_id,
        product_name=product.name,
        supplier_organization_id=item.supplier_organization_id,
        supplier_name=supplier.name,
        warehouse_id=item.warehouse_id,
        region=warehouse.region,
        unit_price=decimal_string(item.amount_minor),
        currency=item.currency,
        minimum_order_quantity=item.minimum_order_quantity,
        available_quantity=balance.effective_sellable_quantity,
        version=item.version,
        is_active=item.is_active,
        demo_run_id=item.demo_run_id,
    )


def create_offer(
    supplier_id: UUID,
    data: OfferCreate,
    actor: UserResponse,
    factory: sessionmaker[Session],
) -> OfferResponse:
    with transactional_session(factory) as session:
        authorize(session, actor, {Role.SUPPLIER}, write=True)
        if supplier_id != actor.organization_id:
            fail("SUPPLIER_NOT_FOUND", "Fornecedor não encontrado.", 404)
        warehouse = owned_warehouse(session, data.warehouse_id, actor)
        if warehouse.geocoding_state != "CONFIRMED":
            fail(
                "WAREHOUSE_PENDING_REVIEW",
                "Confirme a origem antes de publicar ofertas.",
            )
        product = session.scalar(
            select(Product)
            .where(
                Product.id == data.product_id,
                Product.demo_run_id == actor.demo_run_id,
                Product.publication_state == "PUBLISHED",
            )
            .with_for_update(read=True)
        )
        if product is None:
            fail("PRODUCT_NOT_FOUND", "Variante publicada não encontrada.", 404)
        item = Offer(
            product_id=product.id,
            warehouse_id=data.warehouse_id,
            supplier_organization_id=supplier_id,
            amount_minor=minor(data.unit_price),
            currency=data.currency,
            minimum_order_quantity=data.minimum_order_quantity,
            demo_run_id=actor.demo_run_id,
        )
        session.add(item)
        session.flush()
        session.add(
            OfferPriceVersion(
                offer_id=item.id,
                version=1,
                amount_minor=item.amount_minor,
                currency=item.currency,
                minimum_order_quantity=item.minimum_order_quantity,
            )
        )
        initialize_projection(session, item)
        session.flush()
        return offer_response(session, item)


def edit_offer(
    offer_id: UUID,
    data: PriceChange | None,
    expected_version: int,
    actor: UserResponse,
    factory: sessionmaker[Session],
) -> OfferResponse:
    with transactional_session(factory) as session:
        authorize(session, actor, {Role.SUPPLIER}, write=True)
        item = session.scalar(
            select(Offer)
            .where(
                Offer.id == offer_id,
                Offer.supplier_organization_id == actor.organization_id,
                Offer.demo_run_id == actor.demo_run_id,
            )
            .with_for_update()
        )
        if item is None:
            fail("OFFER_NOT_FOUND", "Oferta não encontrada.", 404)
        check_version(item.version, expected_version)
        item.version += 1
        if data:
            item.amount_minor = minor(data.unit_price)
            item.minimum_order_quantity = data.minimum_order_quantity
            session.add(
                OfferPriceVersion(
                    offer_id=item.id,
                    version=item.version,
                    amount_minor=item.amount_minor,
                    currency=item.currency,
                    minimum_order_quantity=item.minimum_order_quantity,
                )
            )
        else:
            item.is_active = False
        session.flush()
        return offer_response(session, item)


def list_offers(
    filters: OfferFilters,
    actor: UserResponse,
    factory: sessionmaker[Session],
    page: int,
    page_size: int,
) -> Page[OfferResponse]:
    with transactional_session(factory) as session:
        authorize(session, actor)
        query = (
            select(Offer)
            .join(Product, Product.id == Offer.product_id)
            .join(Warehouse, Warehouse.id == Offer.warehouse_id)
            .where(
                Offer.demo_run_id == actor.demo_run_id,
                Product.demo_run_id == actor.demo_run_id,
                Product.publication_state == "PUBLISHED",
                Offer.is_active.is_(True),
                Warehouse.is_active.is_(True),
            )
        )
        if filters.product_id:
            query = query.where(Offer.product_id == filters.product_id)
        if filters.supplier_id:
            query = query.where(Offer.supplier_organization_id == filters.supplier_id)
        if filters.region:
            query = query.where(Warehouse.region == filters.region)
        if filters.window_start or filters.window_end:
            capacity = select(CapacitySlot.id).where(
                CapacitySlot.warehouse_id == Warehouse.id,
                CapacitySlot.total_quantity > CapacitySlot.reserved_quantity,
            )
            if filters.window_start:
                if filters.window_start.tzinfo is None:
                    fail("WINDOW_INVALID", "Informe janela com fuso.", 422)
                capacity = capacity.where(
                    CapacitySlot.starts_at >= filters.window_start
                )
            if filters.window_end:
                if filters.window_end.tzinfo is None:
                    fail("WINDOW_INVALID", "Informe janela com fuso.", 422)
                capacity = capacity.where(CapacitySlot.ends_at <= filters.window_end)
            query = query.where(exists(capacity))
        total = session.scalar(select(func.count()).select_from(query.subquery()))
        return Page(
            items=[
                offer_response(session, item)
                for item in session.scalars(
                    query.order_by(Offer.id)
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ],
            total=total,
            page=page,
            page_size=page_size,
        )
