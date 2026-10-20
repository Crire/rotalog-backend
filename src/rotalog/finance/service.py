"""Adaptador de pagamento simulado, executado atomicamente sem rede ou PSP real."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from rotalog.core.contracts import fail
from rotalog.core.database import transactional_session
from rotalog.core.money import decimal_string
from rotalog.finance.models import Payment, PaymentAllocation
from rotalog.identity.models import Role
from rotalog.identity.schemas import UserResponse
from rotalog.identity.service import authorize
from rotalog.ordering.models import OrderItem, Purchase, SupplierOrder


def capture_simulated(session: Session, purchase_id: UUID, items: list) -> Payment:
    payment = Payment(
        purchase_id=purchase_id,
        amount_minor=sum(item.amount_minor * item.requested_quantity for item in items),
        state="CAPTURED",
        provider="SIMULATED",
    )
    session.add(payment)
    session.flush()
    for item in items:
        session.add(
            PaymentAllocation(
                payment_id=payment.id,
                order_item_id=item.id,
                amount_minor=item.amount_minor * item.requested_quantity,
                quantity=item.requested_quantity,
            )
        )
    return payment


def refund_refused(
    session: Session, item_id: UUID, amount_minor: int, quantity: int
) -> None:
    allocation = session.scalar(
        select(PaymentAllocation)
        .where(PaymentAllocation.order_item_id == item_id)
        .with_for_update()
    )
    allocation.refunded_minor = amount_minor
    allocation.refunded_quantity = quantity
    allocation.state = (
        "REFUNDED" if quantity == allocation.quantity else "PARTIALLY_REFUNDED"
    )


def payments(
    purchase_id: UUID, actor: UserResponse, factory: sessionmaker[Session]
) -> list[dict]:
    with transactional_session(factory) as session:
        authorize(session, actor, {Role.BUYER})
        purchase = session.scalar(
            select(Purchase).where(
                Purchase.id == purchase_id,
                Purchase.buyer_organization_id == actor.organization_id,
                Purchase.demo_run_id == actor.demo_run_id,
            )
        )
        if purchase is None:
            fail("PURCHASE_NOT_FOUND", "Compra não encontrada.", 404)
        return [
            {
                "id": str(item.id),
                "amount": decimal_string(item.amount_minor),
                "currency": item.currency,
                "state": item.state,
                "provider": item.provider,
                "is_synthetic": True,
            }
            for item in session.scalars(
                select(Payment).where(Payment.purchase_id == purchase.id)
            )
        ]


def financial_summary(
    order_id: UUID, actor: UserResponse, factory: sessionmaker[Session]
) -> dict:
    with transactional_session(factory) as session:
        authorize(session, actor, {Role.BUYER, Role.SUPPLIER})
        order = session.scalar(
            select(SupplierOrder).where(
                SupplierOrder.id == order_id,
                SupplierOrder.demo_run_id == actor.demo_run_id,
                (SupplierOrder.supplier_organization_id == actor.organization_id)
                | (SupplierOrder.buyer_organization_id == actor.organization_id),
            )
        )
        if order is None:
            fail("SUPPLIER_ORDER_NOT_FOUND", "Pedido não encontrado.", 404)
        allocations = session.scalars(
            select(PaymentAllocation)
            .join(OrderItem)
            .where(OrderItem.supplier_order_id == order.id)
        ).all()
        return {
            "supplier_order_id": str(order.id),
            "currency": "BRL",
            "is_synthetic": True,
            "captured": decimal_string(sum(item.amount_minor for item in allocations)),
            "refunded": decimal_string(
                sum(item.refunded_minor for item in allocations)
            ),
            "protected": decimal_string(
                sum(item.amount_minor - item.refunded_minor for item in allocations)
            ),
            "released": "0.00",
            "provider": "SIMULATED",
        }
