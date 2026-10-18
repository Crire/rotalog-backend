"""Registro explícito dos modelos para migrações e ferramentas de banco."""

from rotalog.demo.models import DemoRun
from rotalog.identity.models import LoginThrottle, User
from rotalog.marketplace.models import InventoryBalance, Offer, Product
from rotalog.organizations.models import Organization

__all__ = [
    "DemoRun",
    "InventoryBalance",
    "LoginThrottle",
    "Offer",
    "Organization",
    "Product",
    "User",
]
