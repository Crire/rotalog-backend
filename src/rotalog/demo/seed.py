"""Seed opt-in: python -m rotalog.demo.seed. Nunca executado no bootstrap."""

import os
from getpass import getpass
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

import rotalog.core.models  # noqa: F401
from rotalog.core.config import Environment, Settings, get_settings
from rotalog.core.database import (
    create_database_engine,
    create_session_factory,
    transactional_session,
)
from rotalog.demo.fixtures import DEMO_NAME, DEMO_RUN_ID, PRODUCTS, USERS
from rotalog.demo.models import DemoRun
from rotalog.identity.models import User
from rotalog.identity.security import password_hash, require_demo
from rotalog.marketplace.models import InventoryBalance, Offer, Product
from rotalog.organizations.models import Organization


def seed_demo(
    factory: sessionmaker[Session],
    settings: Settings,
    password: str,
) -> None:
    """Cria uma execução e seu dataset em uma única transação, sem sobrescrever dados."""
    require_demo(settings)
    if settings.environment not in {Environment.DEVELOPMENT, Environment.TEST}:
        raise ValueError("Seed disponível somente em development/test")
    if len(password) < 12 or len(password) > 1024:
        raise ValueError("A senha da demo deve ter entre 12 e 1024 caracteres")
    with transactional_session(factory) as session:
        # Serializa seeds concorrentes do mesmo dataset, inclusive antes da primeira escrita.
        session.execute(text("SELECT pg_advisory_xact_lock(20261018)"))
        if session.get(DemoRun, DEMO_RUN_ID) is not None:
            return
        session.add(DemoRun(id=DEMO_RUN_ID, name=DEMO_NAME))
        session.flush()
        organization_ids = {}
        for user_id, role, organization_name in USERS:
            organization_id = uuid4()
            organization_ids[role] = organization_id
            session.add(
                Organization(
                    id=organization_id,
                    name=organization_name,
                    demo_run_id=DEMO_RUN_ID,
                )
            )
            session.flush()
            session.add(
                User(
                    id=user_id,
                    email=f"{role}@demo.rotalog.invalid",
                    name=f"{role.capitalize()} Sintético",
                    role=role,
                    password_hash=password_hash.hash(password),
                    organization_id=organization_id,
                    demo_run_id=DEMO_RUN_ID,
                )
            )
        session.flush()
        for product_id, name, price in PRODUCTS:
            session.add(Product(id=product_id, name=name, demo_run_id=DEMO_RUN_ID))
            session.flush()
            offer_id = uuid4()
            session.add(
                Offer(
                    id=offer_id,
                    product_id=product_id,
                    supplier_organization_id=organization_ids["fornecedor"],
                    unit_price=price,
                    minimum_order_quantity=1,
                    demo_run_id=DEMO_RUN_ID,
                )
            )
            session.flush()
            session.add(
                InventoryBalance(
                    offer_id=offer_id,
                    available_quantity=100,
                    reserved_quantity=0,
                    demo_run_id=DEMO_RUN_ID,
                )
            )


def main() -> None:
    settings = get_settings()
    require_demo(settings)
    password = os.getenv("ROTALOG_DEMO_PASSWORD") or getpass(
        "Senha para as 3 contas sintéticas: "
    )
    engine = create_database_engine(settings.database_url.get_secret_value())
    try:
        seed_demo(create_session_factory(engine), settings, password)
    finally:
        engine.dispose()
    print(
        "SIMULAÇÃO: dataset pitch-v1-sintetico disponível. Nenhum dado real foi criado."
    )


if __name__ == "__main__":
    main()
