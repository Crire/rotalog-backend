"""Consulta paginada de ofertas da mesma execução sintética do usuário."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from rotalog.core.database import transactional_session
from rotalog.core.errors import RotaLogError
from rotalog.demo.service import require_active_run
from rotalog.identity.schemas import UserResponse
from rotalog.identity.service import require_supplier
from rotalog.marketplace.models import InventoryBalance, Offer, Product
from rotalog.marketplace.schemas import (
    InventoryResponse,
    InventoryUpdate,
    OfferCreate,
    OfferPage,
    OfferResponse,
    ProductCreate,
    ProductResponse,
)
from rotalog.organizations.models import Organization


def _supplier_organization(session: Session, user: UserResponse) -> Organization:
    organization = session.scalar(
        select(Organization).where(
            Organization.id == user.organization_id,
            Organization.demo_run_id == user.demo_run_id,
        )
    )
    if organization is None:
        raise RotaLogError(
            code="ORGANIZATION_UNAVAILABLE",
            message="Organização indisponível.",
            status_code=403,
        )
    return organization


def create_product(
    data: ProductCreate,
    user: UserResponse,
    factory: sessionmaker[Session],
) -> ProductResponse:
    require_supplier(user)
    with transactional_session(factory) as session:
        require_active_run(session, user.demo_run_id)
        _supplier_organization(session, user)
        product = Product(name=data.name, demo_run_id=user.demo_run_id)
        session.add(product)
        session.flush()
        return ProductResponse.model_validate(product)


def create_offer(
    data: OfferCreate,
    user: UserResponse,
    factory: sessionmaker[Session],
) -> OfferResponse:
    require_supplier(user)
    with transactional_session(factory) as session:
        require_active_run(session, user.demo_run_id)
        organization = _supplier_organization(session, user)
        product = session.scalar(
            select(Product).where(
                Product.id == data.product_id,
                Product.demo_run_id == user.demo_run_id,
            )
        )
        if product is None:
            raise RotaLogError(
                code="PRODUCT_NOT_FOUND",
                message="Produto não encontrado.",
                status_code=404,
            )
        offer = Offer(
            product_id=product.id,
            supplier_organization_id=organization.id,
            unit_price=data.unit_price,
            minimum_order_quantity=data.minimum_order_quantity,
            demo_run_id=user.demo_run_id,
        )
        session.add(offer)
        session.flush()
        session.add(
            InventoryBalance(
                offer_id=offer.id,
                available_quantity=data.available_quantity,
                reserved_quantity=0,
                demo_run_id=user.demo_run_id,
            )
        )
        session.flush()
        return OfferResponse(
            id=offer.id,
            product_id=product.id,
            product_name=product.name,
            supplier_organization_id=organization.id,
            supplier_name=organization.name,
            unit_price=offer.unit_price,
            minimum_order_quantity=offer.minimum_order_quantity,
            available_quantity=data.available_quantity,
            demo_run_id=user.demo_run_id,
        )


def _owned_balance(
    session: Session,
    offer_id: UUID,
    user: UserResponse,
    *,
    lock: bool = False,
) -> InventoryBalance:
    _supplier_organization(session, user)
    query = (
        select(InventoryBalance)
        .join(Offer, Offer.id == InventoryBalance.offer_id)
        .where(
            Offer.id == offer_id,
            Offer.supplier_organization_id == user.organization_id,
            Offer.demo_run_id == user.demo_run_id,
            InventoryBalance.demo_run_id == user.demo_run_id,
        )
    )
    if lock:
        query = query.with_for_update(of=InventoryBalance)
    balance = session.scalar(query)
    if balance is None:
        raise RotaLogError(
            code="OFFER_NOT_FOUND",
            message="Oferta não encontrada.",
            status_code=404,
        )
    return balance


def _inventory_response(balance: InventoryBalance) -> InventoryResponse:
    return InventoryResponse(
        offer_id=balance.offer_id,
        declared_quantity=balance.available_quantity,
        reserved_quantity=balance.reserved_quantity,
        available_quantity=balance.available_quantity - balance.reserved_quantity,
        demo_run_id=balance.demo_run_id,
    )


def get_inventory(
    offer_id: UUID,
    user: UserResponse,
    factory: sessionmaker[Session],
) -> InventoryResponse:
    require_supplier(user)
    with transactional_session(factory) as session:
        return _inventory_response(_owned_balance(session, offer_id, user))


def update_inventory(
    offer_id: UUID,
    data: InventoryUpdate,
    user: UserResponse,
    factory: sessionmaker[Session],
) -> InventoryResponse:
    require_supplier(user)
    with transactional_session(factory) as session:
        require_active_run(session, user.demo_run_id)
        balance = _owned_balance(session, offer_id, user, lock=True)
        if data.available_quantity < balance.reserved_quantity:
            raise RotaLogError(
                code="INVENTORY_BELOW_RESERVED",
                message="O estoque declarado não pode ser inferior às reservas existentes.",
                status_code=409,
            )
        balance.available_quantity = data.available_quantity
        session.flush()
        return _inventory_response(balance)


def list_offers(
    user: UserResponse,
    factory: sessionmaker[Session],
    page: int,
    page_size: int,
) -> OfferPage:
    query = (
        select(Offer, Product.name, Organization.name, InventoryBalance)
        .join(Product, Product.id == Offer.product_id)
        .join(Organization, Organization.id == Offer.supplier_organization_id)
        .join(InventoryBalance, InventoryBalance.offer_id == Offer.id)
        .where(
            Offer.demo_run_id == user.demo_run_id,
            Product.demo_run_id == user.demo_run_id,
            Organization.demo_run_id == user.demo_run_id,
            InventoryBalance.demo_run_id == user.demo_run_id,
        )
    )
    with transactional_session(factory) as session:
        total = session.scalar(select(func.count()).select_from(query.subquery()))
        rows = session.execute(
            query.order_by(Product.name, Offer.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return OfferPage(
            items=[
                OfferResponse(
                    id=offer.id,
                    product_id=offer.product_id,
                    product_name=product_name,
                    supplier_organization_id=offer.supplier_organization_id,
                    supplier_name=supplier_name,
                    unit_price=offer.unit_price,
                    minimum_order_quantity=offer.minimum_order_quantity,
                    available_quantity=balance.available_quantity
                    - balance.reserved_quantity,
                    demo_run_id=offer.demo_run_id,
                )
                for offer, product_name, supplier_name, balance in rows
            ],
            total=total or 0,
            page=page,
            page_size=page_size,
        )
