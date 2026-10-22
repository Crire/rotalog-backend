"""Registro explícito dos modelos para migrações e ferramentas de banco."""

from rotalog.catalog.models import Offer, OfferPriceVersion, Product
from rotalog.demo.models import DemoRun
from rotalog.finance.models import Payment, PaymentAllocation
from rotalog.identity.models import AuthSession, LoginThrottle, RefreshToken, User
from rotalog.inventory.models import (
    CapacitySlot,
    InventoryAdjustment,
    InventoryProjection,
    Reservation,
    Warehouse,
)
from rotalog.logistics.models import DeliveryRoute, DriverLocationPoint
from rotalog.operations.models import IdempotencyRecord
from rotalog.ordering.models import (
    CheckoutLine,
    CheckoutSession,
    Fulfillment,
    FulfillmentLine,
    OrderItem,
    Purchase,
    SupplierOrder,
)
from rotalog.organizations.models import Membership, Organization

__all__ = [
    "AuthSession",
    "CapacitySlot",
    "CheckoutLine",
    "CheckoutSession",
    "DeliveryRoute",
    "DemoRun",
    "DriverLocationPoint",
    "Fulfillment",
    "FulfillmentLine",
    "IdempotencyRecord",
    "InventoryAdjustment",
    "InventoryProjection",
    "LoginThrottle",
    "Membership",
    "Offer",
    "OfferPriceVersion",
    "OrderItem",
    "Organization",
    "Payment",
    "PaymentAllocation",
    "Product",
    "Purchase",
    "RefreshToken",
    "Reservation",
    "SupplierOrder",
    "User",
    "Warehouse",
]
