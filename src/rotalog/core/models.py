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
from rotalog.logistics.delivery_models import (
    CustodyEvent,
    DeliveryAttempt,
    DeliveryOutcomeLine,
    DeliveryProof,
    DeliveryProofLineEvidence,
    OrderEvent,
    PrivateEvidence,
    Route,
    RouteAssignment,
    RouteLoad,
    RoutePlanVersion,
    RouteStop,
    Vehicle,
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
    "CustodyEvent",
    "DeliveryAttempt",
    "DeliveryOutcomeLine",
    "DeliveryProof",
    "DeliveryProofLineEvidence",
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
    "OrderEvent",
    "OrderItem",
    "Organization",
    "Payment",
    "PaymentAllocation",
    "PrivateEvidence",
    "Product",
    "Purchase",
    "RefreshToken",
    "Reservation",
    "Route",
    "RouteAssignment",
    "RouteLoad",
    "RoutePlanVersion",
    "RouteStop",
    "SupplierOrder",
    "User",
    "Vehicle",
    "Warehouse",
]
