"""Consulta paginada de ofertas da mesma execução sintética do usuário."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from rotalog.core.database import transactional_session
from rotalog.identity.schemas import UserResponse
from rotalog.marketplace.models import InventoryBalance, Offer, Product
from rotalog.marketplace.schemas import OfferPage, OfferResponse
from rotalog.organizations.models import Organization


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
