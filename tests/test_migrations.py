"""Testes de integração das migrações em PostgreSQL."""

from decimal import Decimal
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.exc import IntegrityError

PREVIOUS_SNAPSHOT = "20261013_0001"


def test_demo_migration_preserves_rot004_snapshot(
    alembic_config: Config,
    database_url: str,
) -> None:
    """Preserva produtos, ofertas e saldos anteriores, sem marcá-los como sintéticos."""
    command.upgrade(alembic_config, "20261013_0002")
    product_id, offer_id = uuid4(), uuid4()
    engine = sa.create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                sa.text("INSERT INTO product (id, name) VALUES (:id, 'Anterior')"),
                {"id": product_id},
            )
            connection.execute(
                sa.text(
                    "INSERT INTO offer (id, product_id, supplier_organization_id, "
                    "unit_price, minimum_order_quantity) VALUES (:id, :product, :supplier, 42.50, 1)"
                ),
                {"id": offer_id, "product": product_id, "supplier": uuid4()},
            )
            connection.execute(
                sa.text(
                    "INSERT INTO inventory_balance (offer_id, available_quantity, reserved_quantity) "
                    "VALUES (:offer, 10, 2)"
                ),
                {"offer": offer_id},
            )
        command.upgrade(alembic_config, "head")
        with engine.connect() as connection:
            row = connection.execute(
                sa.text("SELECT unit_price, demo_run_id FROM offer WHERE id = :id"),
                {"id": offer_id},
            ).one()
            assert row.unit_price == Decimal("42.50")
            assert row.demo_run_id is None
            assert connection.execute(
                sa.text(
                    "SELECT available_quantity, reserved_quantity FROM inventory_balance "
                    "WHERE offer_id = :id"
                ),
                {"id": offer_id},
            ).one() == (10, 2)
        command.downgrade(alembic_config, "20261013_0002")
        with engine.connect() as connection:
            assert (
                connection.scalar(
                    sa.text("SELECT name FROM product WHERE id = :id"),
                    {"id": product_id},
                )
                == "Anterior"
            )
    finally:
        engine.dispose()


def test_migrations_run_on_empty_database(
    alembic_config: Config,
    database_url: str,
) -> None:
    command.upgrade(alembic_config, "head")
    command.check(alembic_config)

    engine = sa.create_engine(database_url)
    try:
        inspector = sa.inspect(engine)
        assert {"product", "offer", "inventory_balance"} <= set(
            inspector.get_table_names()
        )

        offer_columns = {
            column["name"]: column for column in inspector.get_columns("offer")
        }
        price_type = offer_columns["unit_price"]["type"]
        assert isinstance(price_type, sa.Numeric)
        assert (price_type.precision, price_type.scale) == (14, 2)

        product_columns = {
            column["name"]: column for column in inspector.get_columns("product")
        }
        assert product_columns["created_at"]["type"].timezone is True
    finally:
        engine.dispose()

    command.downgrade(alembic_config, "base")
    engine = sa.create_engine(database_url)
    try:
        assert not {
            "product",
            "offer",
            "inventory_balance",
        } & set(sa.inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_migrations_preserve_previous_snapshot(
    alembic_config: Config,
    database_url: str,
) -> None:
    command.upgrade(alembic_config, PREVIOUS_SNAPSHOT)
    product_id = uuid4()
    engine = sa.create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                sa.text("INSERT INTO product (id, name) VALUES (:id, :name)"),
                {"id": product_id, "name": "Produto existente"},
            )
    finally:
        engine.dispose()

    command.upgrade(alembic_config, "head")
    engine = sa.create_engine(database_url)
    try:
        with engine.connect() as connection:
            assert (
                connection.scalar(
                    sa.text("SELECT name FROM product WHERE id = :id"),
                    {"id": product_id},
                )
                == "Produto existente"
            )
        assert {"offer", "inventory_balance"} <= set(
            sa.inspect(engine).get_table_names()
        )
    finally:
        engine.dispose()


def test_database_constraints_reject_invalid_values(
    alembic_config: Config,
    database_url: str,
) -> None:
    command.upgrade(alembic_config, "head")
    engine = sa.create_engine(database_url)
    product_id = uuid4()
    supplier_id = uuid4()

    try:
        with engine.begin() as connection:
            connection.execute(
                sa.text("INSERT INTO product (id, name) VALUES (:id, :name)"),
                {"id": product_id, "name": "Produto válido"},
            )

        invalid_offers = (
            {"unit_price": Decimal("-0.01"), "minimum_order_quantity": 1},
            {"unit_price": Decimal("10.00"), "minimum_order_quantity": 0},
        )
        for invalid_values in invalid_offers:
            with pytest.raises(IntegrityError), engine.begin() as connection:
                connection.execute(
                    sa.text(
                        """
                        INSERT INTO offer (
                            id, product_id, supplier_organization_id,
                            unit_price, minimum_order_quantity
                        ) VALUES (
                            :id, :product_id, :supplier_id,
                            :unit_price, :minimum_order_quantity
                        )
                        """
                    ),
                    {
                        "id": uuid4(),
                        "product_id": product_id,
                        "supplier_id": supplier_id,
                        **invalid_values,
                    },
                )

        offer_id = uuid4()
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    """
                    INSERT INTO offer (
                        id, product_id, supplier_organization_id,
                        unit_price, minimum_order_quantity
                    ) VALUES (:id, :product_id, :supplier_id, 10.00, 1)
                    """
                ),
                {
                    "id": offer_id,
                    "product_id": product_id,
                    "supplier_id": supplier_id,
                },
            )

        invalid_balances = ((-1, 0), (1, -1), (1, 2))
        for available_quantity, reserved_quantity in invalid_balances:
            with pytest.raises(IntegrityError), engine.begin() as connection:
                connection.execute(
                    sa.text(
                        """
                        INSERT INTO inventory_balance (
                            id, offer_id, available_quantity, reserved_quantity
                        ) VALUES (
                            :id, :offer_id, :available_quantity, :reserved_quantity
                        )
                        """
                    ),
                    {
                        "id": uuid4(),
                        "offer_id": offer_id,
                        "available_quantity": available_quantity,
                        "reserved_quantity": reserved_quantity,
                    },
                )
    finally:
        engine.dispose()
