"""Migrações reais em PostgreSQL: vazio, snapshots e preservação de valores."""

from decimal import Decimal
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from sqlalchemy.exc import IntegrityError

from rotalog.catalog.models import Offer, Product
from rotalog.core.database import transactional_session
from rotalog.inventory.models import InventoryProjection


def test_migrations_run_on_empty_database(alembic_config, database_url):
    command.upgrade(alembic_config, "head")
    command.check(alembic_config)
    engine = sa.create_engine(database_url)
    try:
        inspector = sa.inspect(engine)
        assert {
            "product",
            "offer",
            "inventory_projection",
            "warehouse",
            "membership",
            "auth_session",
            "refresh_token",
            "checkout_session",
            "purchase",
            "supplier_order",
            "order_item",
            "payment",
            "payment_allocation",
        } <= set(inspector.get_table_names())
        columns = {column["name"]: column for column in inspector.get_columns("offer")}
        assert isinstance(columns["amount_minor"]["type"], sa.BigInteger)
        assert "unit_price" not in columns
        assert {column["name"]: column for column in inspector.get_columns("product")}[
            "created_at"
        ]["type"].timezone
    finally:
        engine.dispose()
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")
    command.check(alembic_config)


@pytest.mark.parametrize(
    "snapshot", ["20261013_0001", "20261013_0002", "20261018_0003"]
)
def test_v5_preserves_previous_snapshots(alembic_config, database_url, snapshot):
    command.upgrade(alembic_config, snapshot)
    product_id, offer_id = uuid4(), uuid4()
    engine = sa.create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO product (id, name) VALUES (:id, 'Produto anterior')"
                ),
                {"id": product_id},
            )
            if snapshot != "20261013_0001":
                connection.execute(
                    sa.text(
                        "INSERT INTO offer (id, product_id, supplier_organization_id, unit_price, minimum_order_quantity) VALUES (:id, :product, :supplier, 42.50, 1)"
                    ),
                    {"id": offer_id, "product": product_id, "supplier": uuid4()},
                )
                connection.execute(
                    sa.text(
                        "INSERT INTO inventory_balance (offer_id, available_quantity, reserved_quantity) VALUES (:id, 10, 2)"
                    ),
                    {"id": offer_id},
                )
        command.upgrade(alembic_config, "head")
        command.check(alembic_config)
        with engine.connect() as connection:
            assert connection.execute(
                sa.text("SELECT name, publication_state FROM product WHERE id=:id"),
                {"id": product_id},
            ).one() == ("Produto anterior", "DRAFT")
            if snapshot != "20261013_0001":
                assert connection.execute(
                    sa.text("SELECT amount_minor, currency FROM offer WHERE id=:id"),
                    {"id": offer_id},
                ).one() == (4250, "BRL")
                assert connection.execute(
                    sa.text(
                        "SELECT external_sellable_quantity, rotalog_reserved_not_reflected_quantity FROM inventory_projection WHERE offer_id=:id"
                    ),
                    {"id": offer_id},
                ).one() == (10, 2)
        command.downgrade(alembic_config, snapshot)
        with engine.connect() as connection:
            assert (
                connection.scalar(
                    sa.text("SELECT name FROM product WHERE id=:id"), {"id": product_id}
                )
                == "Produto anterior"
            )
            if snapshot != "20261013_0001":
                assert connection.scalar(
                    sa.text("SELECT unit_price FROM offer WHERE id=:id"),
                    {"id": offer_id},
                ) == Decimal("42.50")
                assert connection.execute(
                    sa.text(
                        "SELECT available_quantity, reserved_quantity FROM inventory_balance WHERE offer_id=:id"
                    ),
                    {"id": offer_id},
                ).one() == (10, 2)
    finally:
        engine.dispose()


def test_database_constraints_reject_invalid_values(demo_client):
    factory = demo_client.app.state.session_factory
    with transactional_session(factory) as session:
        product_id = session.scalar(sa.select(Product.id))
    for amount, minimum in [(-1, 1), (1000, 0)]:
        with pytest.raises(IntegrityError), transactional_session(factory) as session:
            session.add(
                Offer(
                    product_id=product_id,
                    supplier_organization_id=uuid4(),
                    amount_minor=amount,
                    minimum_order_quantity=minimum,
                )
            )
    for total, reserved, safety in [(-1, 0, 0), (1, -1, 0), (1, 2, 0), (1, 1, 1)]:
        with pytest.raises(IntegrityError), transactional_session(factory) as session:
            offer = Offer(
                product_id=product_id,
                supplier_organization_id=uuid4(),
                amount_minor=1000,
                minimum_order_quantity=1,
            )
            session.add(offer)
            session.flush()
            session.add(
                InventoryProjection(
                    offer_id=offer.id,
                    external_sellable_quantity=total,
                    rotalog_reserved_not_reflected_quantity=reserved,
                    safety_stock_quantity=safety,
                )
            )


def test_downgrade_after_demo_use_is_blocked(demo_client, alembic_config):
    with pytest.raises(RuntimeError, match="Downgrade V5 bloqueado"):
        command.downgrade(alembic_config, "20261018_0003")


def test_v41_identity_membership_and_stock_are_preserved(alembic_config, database_url):
    command.upgrade(alembic_config, "20261018_0003")
    identifiers = {name: uuid4() for name in ("run", "org", "user", "product", "offer")}
    engine = sa.create_engine(database_url)
    try:
        with engine.begin() as connection:
            for sql in [
                "INSERT INTO demo_run (id,name) VALUES (:run, 'execução anterior sintética')",
                "INSERT INTO organization (id,name,demo_run_id) VALUES (:org,'Fornecedor anterior',:run)",
                "INSERT INTO identity_user (id,email,name,password_hash,role,organization_id,demo_run_id) VALUES (:user,'anterior@demo.rotalog.invalid','Anterior','hash-anterior-preservado','fornecedor',:org,:run)",
                "INSERT INTO product (id,name,demo_run_id) VALUES (:product,'Variante anterior',:run)",
                "INSERT INTO offer (id,product_id,supplier_organization_id,unit_price,minimum_order_quantity,demo_run_id) VALUES (:offer,:product,:org,29.90,1,:run)",
                "INSERT INTO inventory_balance (offer_id,available_quantity,reserved_quantity,demo_run_id) VALUES (:offer,20,3,:run)",
            ]:
                connection.execute(sa.text(sql), identifiers)
        command.upgrade(alembic_config, "head")
        command.check(alembic_config)
        with engine.connect() as connection:
            assert connection.execute(
                sa.text("SELECT role,password_hash FROM identity_user WHERE id=:user"),
                identifiers,
            ).one() == ("SUPPLIER_OPERATOR", "hash-anterior-preservado")
            assert (
                connection.scalar(
                    sa.text(
                        "SELECT role FROM membership WHERE user_id=:user AND organization_id=:org"
                    ),
                    identifiers,
                )
                == "SUPPLIER_OPERATOR"
            )
            assert (
                connection.scalar(
                    sa.text("SELECT kind FROM organization WHERE id=:org"), identifiers
                )
                == "SUPPLIER"
            )
            row = connection.execute(
                sa.text(
                    "SELECT o.amount_minor,o.warehouse_id,p.warehouse_id,p.external_sellable_quantity,p.rotalog_reserved_not_reflected_quantity FROM offer o JOIN inventory_projection p ON p.offer_id=o.id WHERE o.id=:offer"
                ),
                identifiers,
            ).one()
            assert row[0] == 2990 and row[1] == row[2] and row[1] is not None
            assert tuple(row[3:]) == (20, 3)
            assert (
                connection.scalar(
                    sa.text(
                        "SELECT freshness_state FROM inventory_projection WHERE offer_id=:offer"
                    ),
                    identifiers,
                )
                == "RECONCILING"
            )
    finally:
        engine.dispose()
