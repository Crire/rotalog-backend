"""API pública de inventário usada pelos casos de uso comerciais na mesma transação."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from rotalog.catalog.models import Offer, Product
from rotalog.core.contracts import Page, check_version, fail
from rotalog.core.database import transactional_session
from rotalog.identity.models import Role
from rotalog.identity.schemas import UserResponse
from rotalog.identity.service import authorize
from rotalog.inventory.models import (
    CapacitySlot,
    InventoryAdjustment,
    InventoryProjection,
    Reservation,
    Warehouse,
)
from rotalog.inventory.schemas import (
    CapacityAdjustment,
    CapacityCreate,
    CapacityResponse,
    GeocodingReview,
    InventoryAdjustmentRequest,
    InventoryResponse,
    WarehouseCreate,
    WarehouseResponse,
)


def owned_warehouse(
    session: Session, warehouse_id: UUID, actor: UserResponse
) -> Warehouse:
    warehouse = session.scalar(
        select(Warehouse).where(
            Warehouse.id == warehouse_id,
            Warehouse.supplier_organization_id == actor.organization_id,
            Warehouse.demo_run_id == actor.demo_run_id,
            Warehouse.is_active.is_(True),
        )
    )
    if warehouse is None:
        fail("WAREHOUSE_NOT_FOUND", "Depósito não encontrado.", 404)
    return warehouse


def create_warehouse(
    supplier_id: UUID,
    data: WarehouseCreate,
    actor: UserResponse,
    factory: sessionmaker[Session],
) -> WarehouseResponse:
    with transactional_session(factory) as session:
        authorize(session, actor, {Role.SUPPLIER}, write=True)
        if supplier_id != actor.organization_id:
            fail("SUPPLIER_NOT_FOUND", "Fornecedor não encontrado.", 404)
        item = Warehouse(
            **data.model_dump(),
            supplier_organization_id=supplier_id,
            demo_run_id=actor.demo_run_id,
        )
        session.add(item)
        session.flush()
        return WarehouseResponse.model_validate(item)


def list_warehouses(
    actor: UserResponse, factory: sessionmaker[Session], page: int, page_size: int
) -> Page[WarehouseResponse]:
    with transactional_session(factory) as session:
        authorize(session, actor, {Role.SUPPLIER})
        query = select(Warehouse).where(
            Warehouse.supplier_organization_id == actor.organization_id,
            Warehouse.demo_run_id == actor.demo_run_id,
        )
        total = session.scalar(select(func.count()).select_from(query.subquery()))
        items = session.scalars(
            query.order_by(Warehouse.id).offset((page - 1) * page_size).limit(page_size)
        )
        return Page(
            items=[WarehouseResponse.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )


def initialize_projection(session: Session, offer: Offer) -> None:
    session.add(
        InventoryProjection(
            offer_id=offer.id,
            warehouse_id=offer.warehouse_id,
            external_sellable_quantity=0,
            demo_run_id=offer.demo_run_id,
        )
    )


def review_geocoding(
    warehouse_id: UUID,
    data: GeocodingReview,
    actor: UserResponse,
    factory: sessionmaker[Session],
) -> WarehouseResponse:
    with transactional_session(factory) as session:
        authorize(session, actor, {Role.ADMIN}, write=True)
        warehouse = session.scalar(
            select(Warehouse)
            .where(
                Warehouse.id == warehouse_id, Warehouse.demo_run_id == actor.demo_run_id
            )
            .with_for_update()
        )
        if warehouse is None:
            fail("WAREHOUSE_NOT_FOUND", "Depósito não encontrado.", 404)
        check_version(warehouse.version, data.expected_version)
        warehouse.latitude, warehouse.longitude = data.latitude, data.longitude
        warehouse.geocoding_state = "CONFIRMED"
        warehouse.geocoding_review_reason, warehouse.reviewed_by = data.reason, actor.id
        warehouse.version += 1
        session.flush()
        return WarehouseResponse.model_validate(warehouse)


def list_inventory(
    actor: UserResponse,
    factory: sessionmaker[Session],
    page: int,
    page_size: int,
    warehouse_id: UUID | None = None,
    offer_id: UUID | None = None,
) -> Page[InventoryResponse]:
    with transactional_session(factory) as session:
        authorize(session, actor, {Role.SUPPLIER})
        query = (
            select(InventoryProjection)
            .join(Offer, Offer.id == InventoryProjection.offer_id)
            .where(
                Offer.supplier_organization_id == actor.organization_id,
                Offer.demo_run_id == actor.demo_run_id,
                InventoryProjection.demo_run_id == actor.demo_run_id,
                InventoryProjection.warehouse_id.is_not(None),
            )
        )
        if warehouse_id:
            query = query.where(InventoryProjection.warehouse_id == warehouse_id)
        if offer_id:
            query = query.where(InventoryProjection.offer_id == offer_id)
        total = session.scalar(select(func.count()).select_from(query.subquery()))
        return Page(
            items=[
                InventoryResponse.model_validate(item).model_copy(
                    update={
                        "product_id": session.get(Offer, item.offer_id).product_id,
                        "product_name": session.get(
                            Product, session.get(Offer, item.offer_id).product_id
                        ).name,
                        "offer_active": session.get(Offer, item.offer_id).is_active,
                    }
                )
                for item in session.scalars(
                    query.order_by(InventoryProjection.id)
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ],
            total=total,
            page=page,
            page_size=page_size,
        )


def adjust_inventory(
    data: InventoryAdjustmentRequest,
    actor: UserResponse,
    factory: sessionmaker[Session],
) -> InventoryResponse:
    with transactional_session(factory) as session:
        authorize(session, actor, {Role.SUPPLIER}, write=True)
        owned_warehouse(session, data.warehouse_id, actor)
        item = session.scalar(
            select(InventoryProjection)
            .join(Offer, Offer.id == InventoryProjection.offer_id)
            .where(
                Offer.supplier_organization_id == actor.organization_id,
                Offer.demo_run_id == actor.demo_run_id,
                InventoryProjection.offer_id == data.offer_id,
                InventoryProjection.warehouse_id == data.warehouse_id,
                InventoryProjection.demo_run_id == actor.demo_run_id,
            )
            .with_for_update(of=InventoryProjection)
        )
        if item is None:
            fail("INVENTORY_NOT_FOUND", "Estoque não encontrado.", 404)
        check_version(item.version, data.expected_version)
        if (
            data.external_sellable_quantity
            < item.rotalog_reserved_not_reflected_quantity + data.safety_stock_quantity
        ):
            fail(
                "INVENTORY_BELOW_RESERVED",
                "Saldo não pode consumir reservas ou estoque de segurança.",
            )
        session.add(
            InventoryAdjustment(
                projection_id=item.id,
                actor_id=actor.id,
                reason=data.reason,
                before_quantity=item.external_sellable_quantity,
                after_quantity=data.external_sellable_quantity,
                version=item.version + 1,
            )
        )
        item.external_sellable_quantity = data.external_sellable_quantity
        item.safety_stock_quantity = data.safety_stock_quantity
        item.version += 1
        item.source_observed_at = item.received_at = datetime.now(UTC)
        session.flush()
        return InventoryResponse.model_validate(item)


def create_capacity(
    data: CapacityCreate, actor: UserResponse, factory: sessionmaker[Session]
) -> CapacityResponse:
    with transactional_session(factory) as session:
        authorize(session, actor, {Role.SUPPLIER}, write=True)
        owned_warehouse(session, data.warehouse_id, actor)
        if data.ends_at <= datetime.now(UTC):
            fail("CAPACITY_WINDOW_PAST", "Janela de capacidade já encerrada.", 422)
        item = CapacitySlot(**data.model_dump())
        session.add(item)
        session.flush()
        return CapacityResponse.model_validate(item)


def list_capacity(
    actor: UserResponse,
    factory: sessionmaker[Session],
    warehouse_id: UUID | None,
    page: int,
    page_size: int,
) -> Page[CapacityResponse]:
    with transactional_session(factory) as session:
        authorize(session, actor)
        query = (
            select(CapacitySlot)
            .join(Warehouse, Warehouse.id == CapacitySlot.warehouse_id)
            .where(
                Warehouse.demo_run_id == actor.demo_run_id,
                Warehouse.is_active.is_(True),
                CapacitySlot.ends_at > datetime.now(UTC),
            )
        )
        if warehouse_id:
            query = query.where(Warehouse.id == warehouse_id)
        total = session.scalar(select(func.count()).select_from(query.subquery()))
        return Page(
            items=[
                CapacityResponse.model_validate(item)
                for item in session.scalars(
                    query.order_by(CapacitySlot.starts_at, CapacitySlot.id)
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ],
            total=total,
            page=page,
            page_size=page_size,
        )


def adjust_capacity(
    slot_id: UUID,
    data: CapacityAdjustment,
    actor: UserResponse,
    factory: sessionmaker[Session],
) -> CapacityResponse:
    with transactional_session(factory) as session:
        authorize(session, actor, {Role.SUPPLIER}, write=True)
        item = session.scalar(
            select(CapacitySlot)
            .join(Warehouse)
            .where(
                CapacitySlot.id == slot_id,
                Warehouse.supplier_organization_id == actor.organization_id,
                Warehouse.demo_run_id == actor.demo_run_id,
            )
            .with_for_update(of=CapacitySlot)
        )
        if item is None:
            fail("CAPACITY_NOT_FOUND", "Capacidade não encontrada.", 404)
        check_version(item.version, data.expected_version)
        if data.total_quantity < item.reserved_quantity:
            fail("CAPACITY_BELOW_RESERVED", "Capacidade inferior às reservas.")
        item.adjustments = [
            *item.adjustments,
            {
                "actor_id": str(actor.id),
                "reason": data.reason,
                "before": item.total_quantity,
                "after": data.total_quantity,
            },
        ]
        item.total_quantity = data.total_quantity
        item.version += 1
        session.flush()
        return CapacityResponse.model_validate(item)


def reserve(
    session: Session,
    checkout_id: UUID,
    offer_id: UUID,
    warehouse_id: UUID,
    slot: CapacitySlot,
    quantity: int,
    expires_at: datetime,
) -> InventoryProjection:
    item = session.scalar(
        select(InventoryProjection)
        .where(
            InventoryProjection.offer_id == offer_id,
            InventoryProjection.warehouse_id == warehouse_id,
        )
        .with_for_update()
    )
    if (
        item is None
        or item.freshness_state != "FRESH"
        or item.effective_sellable_quantity < quantity
    ):
        fail("INSUFFICIENT_INVENTORY", "Estoque indisponível ou insuficiente.")
    if slot.total_quantity - slot.reserved_quantity < quantity:
        fail("INSUFFICIENT_CAPACITY", "Capacidade insuficiente na janela.")
    item.rotalog_reserved_not_reflected_quantity += quantity
    item.version += 1
    slot.reserved_quantity += quantity
    slot.version += 1
    session.add(
        Reservation(
            checkout_id=checkout_id,
            projection_id=item.id,
            capacity_slot_id=slot.id,
            quantity=quantity,
            expires_at=expires_at,
        )
    )
    return item


def release(
    session: Session, reservation: Reservation, quantity: int, *, expired: bool = False
) -> None:
    if quantity <= 0:
        return
    if (
        quantity
        > reservation.quantity
        - reservation.released_quantity
        - reservation.consumed_quantity
    ):
        fail(
            "RESERVATION_ALREADY_CONSUMED",
            "Não é possível liberar reserva já consumida na coleta.",
        )
    item = session.scalar(
        select(InventoryProjection)
        .where(InventoryProjection.id == reservation.projection_id)
        .with_for_update()
    )
    slot = session.scalar(
        select(CapacitySlot)
        .where(CapacitySlot.id == reservation.capacity_slot_id)
        .with_for_update()
    )
    item.rotalog_reserved_not_reflected_quantity -= quantity
    item.version += 1
    slot.reserved_quantity -= quantity
    slot.version += 1
    reservation.released_quantity += quantity
    if reservation.released_quantity == reservation.quantity:
        reservation.state = "EXPIRED" if expired else "RELEASED"


def convert_reservations(
    session: Session, checkout_id: UUID
) -> dict[UUID, Reservation]:
    rows = session.scalars(
        select(Reservation)
        .where(Reservation.checkout_id == checkout_id)
        .order_by(Reservation.projection_id)
    ).all()
    result = {}
    for row in rows:
        projection = session.scalar(
            select(InventoryProjection)
            .where(InventoryProjection.id == row.projection_id)
            .with_for_update()
        )
        if (
            row.state != "ACTIVE"
            or row.expires_at <= datetime.now(UTC)
            or projection.freshness_state != "FRESH"
        ):
            fail("RESERVATION_UNAVAILABLE", "Reserva expirada ou estoque indisponível.")
        row.state = "CONVERTED"
        result[projection.offer_id] = row
    return result
