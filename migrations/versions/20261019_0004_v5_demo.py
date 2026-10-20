"""V5: centavos, sessões, variantes, depósitos, reservas e compra sintética.

Revisão aditiva: preserva UUIDs, preços e saldos anteriores. Dados históricos sem
variante completa permanecem DRAFT; depósitos sem origem conhecida ficam nulos.
Downgrade após uso comercial é bloqueado para não apagar transações essenciais.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261019_0004"
down_revision = "20261018_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "identity_user",
        sa.Column("auth_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.drop_constraint(
        op.f("ck_identity_user_role_valid"), "identity_user", type_="check"
    )
    op.alter_column("identity_user", "role", type_=sa.String(32))
    op.execute(
        "UPDATE identity_user SET role = CASE role WHEN 'comprador' THEN 'BUYER_ADMIN' WHEN 'fornecedor' THEN 'SUPPLIER_OPERATOR' WHEN 'motorista' THEN 'DRIVER' ELSE role END"
    )
    op.create_check_constraint(
        op.f("ck_identity_user_role_valid"),
        "identity_user",
        "role IN ('BUYER_ADMIN', 'SUPPLIER_OPERATOR', 'DRIVER', 'ROTALOG_ADMIN')",
    )
    op.add_column(
        "organization",
        sa.Column("kind", sa.String(20), nullable=False, server_default="BUYER"),
    )
    op.execute(
        "UPDATE organization SET kind = 'SUPPLIER' WHERE id IN (SELECT organization_id FROM identity_user WHERE role = 'SUPPLIER_OPERATOR')"
    )
    for name, column_type in [
        ("brand", sa.String(200)),
        ("category", sa.String(200)),
        ("gtin", sa.String(14)),
        ("net_content", sa.Integer()),
        ("net_content_unit", sa.String(10)),
        ("packaging_type", sa.String(100)),
        ("packaging_quantity", sa.Integer()),
        ("gross_weight_grams", sa.Integer()),
        ("volume_cm3", sa.Integer()),
    ]:
        op.add_column("product", sa.Column(name, column_type, nullable=True))
    op.add_column(
        "product",
        sa.Column(
            "variant_attributes",
            postgresql.JSONB(),
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column(
        "product",
        sa.Column(
            "publication_state", sa.String(20), nullable=False, server_default="DRAFT"
        ),
    )
    op.add_column(
        "product",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    for name, sql in [
        ("publication_state_valid", "publication_state IN ('DRAFT', 'PUBLISHED')"),
        ("net_content_positive", "net_content IS NULL OR net_content > 0"),
        (
            "packaging_quantity_positive",
            "packaging_quantity IS NULL OR packaging_quantity > 0",
        ),
        ("weight_positive", "gross_weight_grams IS NULL OR gross_weight_grams > 0"),
        ("volume_positive", "volume_cm3 IS NULL OR volume_cm3 > 0"),
    ]:
        op.create_check_constraint(op.f(f"ck_product_{name}"), "product", sql)
    op.drop_constraint(op.f("ck_offer_unit_price_non_negative"), "offer", type_="check")
    op.alter_column(
        "offer",
        "unit_price",
        new_column_name="amount_minor",
        type_=sa.BigInteger(),
        postgresql_using="(unit_price * 100)::bigint",
    )
    op.add_column(
        "offer", sa.Column("currency", sa.CHAR(3), nullable=False, server_default="BRL")
    )
    op.add_column(
        "offer",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "offer", sa.Column("version", sa.Integer(), nullable=False, server_default="1")
    )
    op.add_column("offer", sa.Column("warehouse_id", sa.Uuid(), nullable=True))
    op.create_check_constraint(
        op.f("ck_offer_amount_non_negative"), "offer", "amount_minor >= 0"
    )
    op.create_check_constraint(
        op.f("ck_offer_currency_brl"), "offer", "currency = 'BRL'"
    )

    op.rename_table("inventory_balance", "inventory_projection")
    for name in [
        "available_quantity_non_negative",
        "reserved_quantity_non_negative",
        "reserved_not_greater_than_available",
    ]:
        op.drop_constraint(
            op.f(f"ck_inventory_balance_{name}"), "inventory_projection", type_="check"
        )
    op.drop_constraint(
        "uq_inventory_balance_offer_id", "inventory_projection", type_="unique"
    )
    op.drop_index("ix_inventory_balance_demo_run_id", table_name="inventory_projection")
    op.create_index(
        "ix_inventory_projection_demo_run_id", "inventory_projection", ["demo_run_id"]
    )
    for old, new in [
        ("available_quantity", "external_sellable_quantity"),
        ("reserved_quantity", "rotalog_reserved_not_reflected_quantity"),
    ]:
        op.alter_column("inventory_projection", old, new_column_name=new)
    op.add_column(
        "inventory_projection", sa.Column("warehouse_id", sa.Uuid(), nullable=True)
    )
    op.add_column(
        "inventory_projection",
        sa.Column("external_physical_quantity", sa.Integer(), nullable=True),
    )
    for name, default in [("safety_stock_quantity", "0"), ("version", "1")]:
        op.add_column(
            "inventory_projection",
            sa.Column(name, sa.Integer(), nullable=False, server_default=default),
        )
    for name, size, default in [
        ("external_version", 100, None),
        ("source", 20, "MANUAL"),
        ("freshness_state", 20, "FRESH"),
    ]:
        op.add_column(
            "inventory_projection",
            sa.Column(
                name, sa.String(size), nullable=default is None, server_default=default
            ),
        )
    for name in ["source_observed_at", "received_at", "last_reconciled_at"]:
        op.add_column(
            "inventory_projection",
            sa.Column(
                name,
                sa.DateTime(timezone=True),
                nullable=name == "last_reconciled_at",
                server_default=sa.func.now() if name != "last_reconciled_at" else None,
            ),
        )
    for old, new in [
        ("pk_inventory_balance", "pk_inventory_projection"),
        (
            "fk_inventory_balance_offer_id_offer",
            "fk_inventory_projection_offer_id_offer",
        ),
        (
            "fk_inventory_balance_demo_run_id_demo_run",
            "fk_inventory_projection_demo_run_id_demo_run",
        ),
    ]:
        op.execute(
            f'ALTER TABLE inventory_projection RENAME CONSTRAINT "{old}" TO "{new}"'
        )
    op.create_unique_constraint(
        "uq_inventory_projection_offer_id",
        "inventory_projection",
        ["offer_id", "warehouse_id"],
    )
    for name, sql in [
        ("sellable_non_negative", "external_sellable_quantity >= 0"),
        (
            "physical_non_negative",
            "external_physical_quantity IS NULL OR external_physical_quantity >= 0",
        ),
        ("reserved_non_negative", "rotalog_reserved_not_reflected_quantity >= 0"),
        ("safety_non_negative", "safety_stock_quantity >= 0"),
        (
            "reserved_within_sellable",
            "rotalog_reserved_not_reflected_quantity + safety_stock_quantity <= external_sellable_quantity",
        ),
    ]:
        op.create_check_constraint(
            op.f(f"ck_inventory_projection_{name}"), "inventory_projection", sql
        )
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "idempotency_record",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("operation", sa.String(length=100), nullable=False),
        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("response", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organization.id"],
            name=op.f("fk_idempotency_record_organization_id_organization"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_idempotency_record")),
        sa.UniqueConstraint(
            "organization_id",
            "operation",
            "key",
            name=op.f("uq_idempotency_record_organization_id"),
        ),
    )
    op.create_table(
        "auth_session",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("client_type", sa.String(length=20), nullable=False),
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["identity_user.id"],
            name=op.f("fk_auth_session_user_id_identity_user"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_session")),
    )
    op.create_table(
        "membership",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organization.id"],
            name=op.f("fk_membership_organization_id_organization"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["identity_user.id"],
            name=op.f("fk_membership_user_id_identity_user"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_membership")),
        sa.UniqueConstraint(
            "user_id", "organization_id", "role", name=op.f("uq_membership_user_id")
        ),
    )
    op.create_table(
        "warehouse",
        sa.Column("supplier_organization_id", sa.Uuid(), nullable=False),
        sa.Column("demo_run_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("address", sa.String(length=500), nullable=False),
        sa.Column("opening_hours", sa.String(length=200), nullable=False),
        sa.Column("region", sa.String(length=100), nullable=False),
        sa.Column(
            "geocoding_state",
            sa.String(length=30),
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column("latitude", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("longitude", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("geocoding_review_reason", sa.String(length=500), nullable=True),
        sa.Column("reviewed_by", sa.Uuid(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "latitude IS NULL OR latitude BETWEEN -90 AND 90",
            name=op.f("ck_warehouse_latitude_valid"),
        ),
        sa.CheckConstraint(
            "longitude IS NULL OR longitude BETWEEN -180 AND 180",
            name=op.f("ck_warehouse_longitude_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["demo_run_id"],
            ["demo_run.id"],
            name=op.f("fk_warehouse_demo_run_id_demo_run"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"],
            ["identity_user.id"],
            name=op.f("fk_warehouse_reviewed_by_identity_user"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["supplier_organization_id"],
            ["organization.id"],
            name=op.f("fk_warehouse_supplier_organization_id_organization"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_warehouse")),
    )
    op.create_table(
        "capacity_slot",
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_quantity", sa.Integer(), nullable=False),
        sa.Column(
            "reserved_quantity", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "adjustments",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "ends_at > starts_at", name=op.f("ck_capacity_slot_window_valid")
        ),
        sa.CheckConstraint(
            "total_quantity >= reserved_quantity AND reserved_quantity >= 0",
            name=op.f("ck_capacity_slot_quantities_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["warehouse_id"],
            ["warehouse.id"],
            name=op.f("fk_capacity_slot_warehouse_id_warehouse"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_capacity_slot")),
    )
    op.create_table(
        "refresh_token",
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["auth_session.id"],
            name=op.f("fk_refresh_token_session_id_auth_session"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refresh_token")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_refresh_token_token_hash")),
    )
    op.create_table(
        "checkout_session",
        sa.Column("buyer_organization_id", sa.Uuid(), nullable=False),
        sa.Column("supplier_organization_id", sa.Uuid(), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("capacity_slot_id", sa.Uuid(), nullable=False),
        sa.Column("demo_run_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "state",
            sa.String(length=32),
            server_default="READY_FOR_PAYMENT",
            nullable=False,
        ),
        sa.Column(
            "accepts_partial", sa.Boolean(), server_default="false", nullable=False
        ),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["buyer_organization_id"],
            ["organization.id"],
            name=op.f("fk_checkout_session_buyer_organization_id_organization"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["capacity_slot_id"],
            ["capacity_slot.id"],
            name=op.f("fk_checkout_session_capacity_slot_id_capacity_slot"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["demo_run_id"],
            ["demo_run.id"],
            name=op.f("fk_checkout_session_demo_run_id_demo_run"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["supplier_organization_id"],
            ["organization.id"],
            name=op.f("fk_checkout_session_supplier_organization_id_organization"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["warehouse_id"],
            ["warehouse.id"],
            name=op.f("fk_checkout_session_warehouse_id_warehouse"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_checkout_session")),
    )
    op.create_table(
        "offer_price_version",
        sa.Column("offer_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.CHAR(length=3), server_default="BRL", nullable=False),
        sa.Column("minimum_order_quantity", sa.Integer(), nullable=False),
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "amount_minor >= 0", name=op.f("ck_offer_price_version_amount_non_negative")
        ),
        sa.CheckConstraint(
            "minimum_order_quantity > 0",
            name=op.f("ck_offer_price_version_minimum_order_quantity_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["offer_id"],
            ["offer.id"],
            name=op.f("fk_offer_price_version_offer_id_offer"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_offer_price_version")),
        sa.UniqueConstraint(
            "offer_id", "version", name=op.f("uq_offer_price_version_offer_id")
        ),
    )
    op.create_table(
        "checkout_line",
        sa.Column("checkout_id", sa.Uuid(), nullable=False),
        sa.Column("offer_id", sa.Uuid(), nullable=False),
        sa.Column("offer_version", sa.Integer(), nullable=False),
        sa.Column(
            "product_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.CHAR(length=3), server_default="BRL", nullable=False),
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "quantity > 0 AND amount_minor >= 0",
            name=op.f("ck_checkout_line_values_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["checkout_id"],
            ["checkout_session.id"],
            name=op.f("fk_checkout_line_checkout_id_checkout_session"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["offer_id"],
            ["offer.id"],
            name=op.f("fk_checkout_line_offer_id_offer"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_checkout_line")),
        sa.UniqueConstraint(
            "checkout_id", "offer_id", name=op.f("uq_checkout_line_checkout_id")
        ),
    )
    op.create_table(
        "inventory_adjustment",
        sa.Column("projection_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("before_quantity", sa.Integer(), nullable=False),
        sa.Column("after_quantity", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["identity_user.id"],
            name=op.f("fk_inventory_adjustment_actor_id_identity_user"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["projection_id"],
            ["inventory_projection.id"],
            name=op.f("fk_inventory_adjustment_projection_id_inventory_projection"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inventory_adjustment")),
    )
    op.create_table(
        "purchase",
        sa.Column("checkout_id", sa.Uuid(), nullable=False),
        sa.Column("buyer_organization_id", sa.Uuid(), nullable=False),
        sa.Column("demo_run_id", sa.Uuid(), nullable=False),
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["buyer_organization_id"],
            ["organization.id"],
            name=op.f("fk_purchase_buyer_organization_id_organization"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["checkout_id"],
            ["checkout_session.id"],
            name=op.f("fk_purchase_checkout_id_checkout_session"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["demo_run_id"],
            ["demo_run.id"],
            name=op.f("fk_purchase_demo_run_id_demo_run"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_purchase")),
        sa.UniqueConstraint("checkout_id", name=op.f("uq_purchase_checkout_id")),
    )
    op.create_table(
        "reservation",
        sa.Column("checkout_id", sa.Uuid(), nullable=False),
        sa.Column("projection_id", sa.Uuid(), nullable=False),
        sa.Column("capacity_slot_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column(
            "released_quantity", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "state", sa.String(length=20), server_default="ACTIVE", nullable=False
        ),
        sa.Column(
            "origin", sa.String(length=20), server_default="CHECKOUT", nullable=False
        ),
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "quantity > 0", name=op.f("ck_reservation_quantity_positive")
        ),
        sa.CheckConstraint(
            "released_quantity >= 0 AND released_quantity <= quantity",
            name=op.f("ck_reservation_released_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["capacity_slot_id"],
            ["capacity_slot.id"],
            name=op.f("fk_reservation_capacity_slot_id_capacity_slot"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["checkout_id"],
            ["checkout_session.id"],
            name=op.f("fk_reservation_checkout_id_checkout_session"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["projection_id"],
            ["inventory_projection.id"],
            name=op.f("fk_reservation_projection_id_inventory_projection"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reservation")),
    )
    op.create_table(
        "payment",
        sa.Column("purchase_id", sa.Uuid(), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.CHAR(length=3), server_default="BRL", nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column(
            "provider", sa.String(length=20), server_default="SIMULATED", nullable=False
        ),
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "amount_minor >= 0", name=op.f("ck_payment_amount_non_negative")
        ),
        sa.ForeignKeyConstraint(
            ["purchase_id"],
            ["purchase.id"],
            name=op.f("fk_payment_purchase_id_purchase"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment")),
        sa.UniqueConstraint("purchase_id", name=op.f("uq_payment_purchase_id")),
    )
    op.create_table(
        "supplier_order",
        sa.Column("purchase_id", sa.Uuid(), nullable=False),
        sa.Column("buyer_organization_id", sa.Uuid(), nullable=False),
        sa.Column("supplier_organization_id", sa.Uuid(), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("demo_run_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "accepts_partial", sa.Boolean(), server_default="false", nullable=False
        ),
        sa.Column("acceptance_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cancellation_reason", sa.String(length=500), nullable=True),
        sa.Column("currency", sa.CHAR(length=3), server_default="BRL", nullable=False),
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["buyer_organization_id"],
            ["organization.id"],
            name=op.f("fk_supplier_order_buyer_organization_id_organization"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["demo_run_id"],
            ["demo_run.id"],
            name=op.f("fk_supplier_order_demo_run_id_demo_run"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["purchase_id"],
            ["purchase.id"],
            name=op.f("fk_supplier_order_purchase_id_purchase"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["supplier_organization_id"],
            ["organization.id"],
            name=op.f("fk_supplier_order_supplier_organization_id_organization"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["warehouse_id"],
            ["warehouse.id"],
            name=op.f("fk_supplier_order_warehouse_id_warehouse"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_supplier_order")),
    )
    op.create_table(
        "fulfillment",
        sa.Column("supplier_order_id", sa.Uuid(), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column(
            "state", sa.String(length=32), server_default="SEPARATING", nullable=False
        ),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["supplier_order_id"],
            ["supplier_order.id"],
            name=op.f("fk_fulfillment_supplier_order_id_supplier_order"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["warehouse_id"],
            ["warehouse.id"],
            name=op.f("fk_fulfillment_warehouse_id_warehouse"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fulfillment")),
    )
    op.create_table(
        "order_item",
        sa.Column("supplier_order_id", sa.Uuid(), nullable=False),
        sa.Column("offer_id", sa.Uuid(), nullable=False),
        sa.Column("reservation_id", sa.Uuid(), nullable=False),
        sa.Column(
            "product_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("offer_version", sa.Integer(), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.CHAR(length=3), server_default="BRL", nullable=False),
        sa.Column("requested_quantity", sa.Integer(), nullable=False),
        sa.Column("reserved_quantity", sa.Integer(), nullable=False),
        sa.Column(
            "supplier_accepted_quantity",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "supplier_refused_quantity",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "requested_quantity > 0 AND amount_minor >= 0",
            name=op.f("ck_order_item_snapshot_valid"),
        ),
        sa.CheckConstraint(
            "reserved_quantity >= 0 AND reserved_quantity <= requested_quantity",
            name=op.f("ck_order_item_reservation_valid"),
        ),
        sa.CheckConstraint(
            "supplier_accepted_quantity >= 0 AND supplier_refused_quantity >= 0 AND supplier_accepted_quantity + supplier_refused_quantity <= requested_quantity",
            name=op.f("ck_order_item_decision_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["offer_id"],
            ["offer.id"],
            name=op.f("fk_order_item_offer_id_offer"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reservation_id"],
            ["reservation.id"],
            name=op.f("fk_order_item_reservation_id_reservation"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["supplier_order_id"],
            ["supplier_order.id"],
            name=op.f("fk_order_item_supplier_order_id_supplier_order"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_order_item")),
        sa.UniqueConstraint(
            "reservation_id", name=op.f("uq_order_item_reservation_id")
        ),
    )
    op.create_table(
        "fulfillment_line",
        sa.Column("fulfillment_id", sa.Uuid(), nullable=False),
        sa.Column("order_item_id", sa.Uuid(), nullable=False),
        sa.Column("allocated_quantity", sa.Integer(), nullable=False),
        sa.Column(
            "separated_quantity", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column(
            "dispatched_quantity", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "allocated_quantity > 0 AND separated_quantity >= 0 AND separated_quantity <= allocated_quantity AND dispatched_quantity >= 0 AND dispatched_quantity <= separated_quantity",
            name=op.f("ck_fulfillment_line_quantities_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["fulfillment_id"],
            ["fulfillment.id"],
            name=op.f("fk_fulfillment_line_fulfillment_id_fulfillment"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["order_item_id"],
            ["order_item.id"],
            name=op.f("fk_fulfillment_line_order_item_id_order_item"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fulfillment_line")),
        sa.UniqueConstraint(
            "fulfillment_id",
            "order_item_id",
            name=op.f("uq_fulfillment_line_fulfillment_id"),
        ),
    )
    op.create_table(
        "payment_allocation",
        sa.Column("payment_id", sa.Uuid(), nullable=False),
        sa.Column("order_item_id", sa.Uuid(), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.CHAR(length=3), server_default="BRL", nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column(
            "refunded_quantity", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column(
            "refunded_minor", sa.BigInteger(), server_default="0", nullable=False
        ),
        sa.Column(
            "state", sa.String(length=20), server_default="PROTECTED", nullable=False
        ),
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "amount_minor >= 0 AND quantity > 0",
            name=op.f("ck_payment_allocation_values_valid"),
        ),
        sa.CheckConstraint(
            "refunded_minor >= 0 AND refunded_minor <= amount_minor",
            name=op.f("ck_payment_allocation_refund_valid"),
        ),
        sa.CheckConstraint(
            "refunded_quantity >= 0 AND refunded_quantity <= quantity",
            name=op.f("ck_payment_allocation_refunded_quantity_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["order_item_id"],
            ["order_item.id"],
            name=op.f("fk_payment_allocation_order_item_id_order_item"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["payment_id"],
            ["payment.id"],
            name=op.f("fk_payment_allocation_payment_id_payment"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_allocation")),
        sa.UniqueConstraint(
            "order_item_id", name=op.f("uq_payment_allocation_order_item_id")
        ),
    )
    # ### end Alembic commands ###

    op.create_index("ix_auth_session_user_id", "auth_session", ["user_id"])
    op.create_index("ix_refresh_token_session_id", "refresh_token", ["session_id"])
    op.create_foreign_key(
        "fk_offer_warehouse_id_warehouse",
        "offer",
        "warehouse",
        ["warehouse_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_inventory_projection_warehouse_id_warehouse",
        "inventory_projection",
        "warehouse",
        ["warehouse_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.execute("""INSERT INTO membership (user_id, organization_id, role, is_active)
        SELECT id, organization_id, role, true FROM identity_user""")
    op.execute("""INSERT INTO warehouse (supplier_organization_id, demo_run_id, name, address, opening_hours, region)
        SELECT id, demo_run_id, 'Origem migrada — confirmar dados', 'Endereço sintético pendente', 'A confirmar', 'PENDENTE'
        FROM organization WHERE kind = 'SUPPLIER'""")
    op.execute("""UPDATE offer SET warehouse_id = w.id FROM warehouse w
        WHERE w.supplier_organization_id = offer.supplier_organization_id AND w.demo_run_id = offer.demo_run_id""")
    op.execute("UPDATE offer SET is_active = false WHERE warehouse_id IS NULL")
    op.execute("""UPDATE inventory_projection SET warehouse_id = offer.warehouse_id FROM offer
        WHERE offer.id = inventory_projection.offer_id""")
    op.execute("""INSERT INTO offer_price_version (offer_id, version, amount_minor, currency, minimum_order_quantity)
        SELECT id, version, amount_minor, currency, minimum_order_quantity FROM offer""")

    # Reservas legadas não têm Reservation canônica: não inventar pedidos nem zerar saldo.
    op.execute(
        "UPDATE inventory_projection SET freshness_state = 'RECONCILING' WHERE rotalog_reserved_not_reflected_quantity > 0"
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM purchase) OR EXISTS(SELECT 1 FROM auth_session) OR EXISTS(SELECT 1 FROM identity_user WHERE role = 'ROTALOG_ADMIN')"
        )
    ):
        raise RuntimeError(
            "Downgrade V5 bloqueado: preserve os dados e use migração compensatória."
        )
    op.drop_constraint("fk_offer_warehouse_id_warehouse", "offer", type_="foreignkey")
    op.drop_constraint(
        "fk_inventory_projection_warehouse_id_warehouse",
        "inventory_projection",
        type_="foreignkey",
    )
    op.drop_table("payment_allocation")
    op.drop_table("fulfillment_line")
    op.drop_table("order_item")
    op.drop_table("fulfillment")
    op.drop_table("supplier_order")
    op.drop_table("payment")
    op.drop_table("reservation")
    op.drop_table("purchase")
    op.drop_table("inventory_adjustment")
    op.drop_table("checkout_line")
    op.drop_table("refresh_token")
    op.drop_table("offer_price_version")
    op.drop_table("checkout_session")
    op.drop_table("membership")
    op.drop_table("capacity_slot")
    op.drop_table("auth_session")
    op.drop_table("warehouse")
    op.drop_table("idempotency_record")

    for name in [
        "sellable_non_negative",
        "physical_non_negative",
        "reserved_non_negative",
        "safety_non_negative",
        "reserved_within_sellable",
    ]:
        op.drop_constraint(
            op.f(f"ck_inventory_projection_{name}"),
            "inventory_projection",
            type_="check",
        )
    op.drop_constraint(
        "uq_inventory_projection_offer_id", "inventory_projection", type_="unique"
    )
    op.drop_index(
        "ix_inventory_projection_demo_run_id", table_name="inventory_projection"
    )
    for name in [
        "warehouse_id",
        "external_physical_quantity",
        "safety_stock_quantity",
        "version",
        "external_version",
        "source",
        "freshness_state",
        "source_observed_at",
        "received_at",
        "last_reconciled_at",
    ]:
        op.drop_column("inventory_projection", name)
    for old, new in [
        ("external_sellable_quantity", "available_quantity"),
        ("rotalog_reserved_not_reflected_quantity", "reserved_quantity"),
    ]:
        op.alter_column("inventory_projection", old, new_column_name=new)
    for old, new in [
        ("pk_inventory_projection", "pk_inventory_balance"),
        (
            "fk_inventory_projection_offer_id_offer",
            "fk_inventory_balance_offer_id_offer",
        ),
        (
            "fk_inventory_projection_demo_run_id_demo_run",
            "fk_inventory_balance_demo_run_id_demo_run",
        ),
    ]:
        op.execute(
            f'ALTER TABLE inventory_projection RENAME CONSTRAINT "{old}" TO "{new}"'
        )
    op.rename_table("inventory_projection", "inventory_balance")
    op.create_index(
        "ix_inventory_balance_demo_run_id", "inventory_balance", ["demo_run_id"]
    )
    op.create_unique_constraint(
        "uq_inventory_balance_offer_id", "inventory_balance", ["offer_id"]
    )
    for name, sql in [
        ("available_quantity_non_negative", "available_quantity >= 0"),
        ("reserved_quantity_non_negative", "reserved_quantity >= 0"),
        (
            "reserved_not_greater_than_available",
            "reserved_quantity <= available_quantity",
        ),
    ]:
        op.create_check_constraint(
            op.f(f"ck_inventory_balance_{name}"), "inventory_balance", sql
        )
    for name in ["amount_non_negative", "currency_brl"]:
        op.drop_constraint(op.f(f"ck_offer_{name}"), "offer", type_="check")
    op.alter_column(
        "offer",
        "amount_minor",
        new_column_name="unit_price",
        type_=sa.Numeric(14, 2),
        postgresql_using="amount_minor::numeric / 100",
    )
    op.create_check_constraint(
        op.f("ck_offer_unit_price_non_negative"), "offer", "unit_price >= 0"
    )
    for name in ["warehouse_id", "currency", "is_active", "version"]:
        op.drop_column("offer", name)
    for name in [
        "publication_state_valid",
        "net_content_positive",
        "packaging_quantity_positive",
        "weight_positive",
        "volume_positive",
    ]:
        op.drop_constraint(op.f(f"ck_product_{name}"), "product", type_="check")
    for name in [
        "brand",
        "category",
        "gtin",
        "net_content",
        "net_content_unit",
        "packaging_type",
        "packaging_quantity",
        "gross_weight_grams",
        "volume_cm3",
        "variant_attributes",
        "publication_state",
        "version",
    ]:
        op.drop_column("product", name)
    op.drop_column("organization", "kind")
    op.drop_column("identity_user", "auth_version")
    op.drop_constraint(
        op.f("ck_identity_user_role_valid"), "identity_user", type_="check"
    )
    op.execute(
        "UPDATE identity_user SET role = CASE role WHEN 'BUYER_ADMIN' THEN 'comprador' WHEN 'SUPPLIER_OPERATOR' THEN 'fornecedor' WHEN 'DRIVER' THEN 'motorista' ELSE role END"
    )
    op.alter_column("identity_user", "role", type_=sa.String(20))
    op.create_check_constraint(
        op.f("ck_identity_user_role_valid"),
        "identity_user",
        "role IN ('comprador', 'fornecedor', 'motorista')",
    )
