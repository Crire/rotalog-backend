"""Cria rotas de entrega e pontos de localização sintéticos."""

import sqlalchemy as sa
from alembic import op


revision = "20261022_0005"
down_revision = "20261019_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "delivery_route",
        sa.Column("supplier_order_id", sa.Uuid(), nullable=False),
        sa.Column("driver_id", sa.Uuid(), nullable=False),
        sa.Column("demo_run_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(length=20), server_default="ASSIGNED", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("last_latitude", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("last_longitude", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("last_accuracy_meters", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("last_location_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("state IN ('ASSIGNED', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED')", name=op.f("ck_delivery_route_state_valid")),
        sa.CheckConstraint("last_latitude IS NULL OR last_latitude BETWEEN -90 AND 90", name=op.f("ck_delivery_route_last_latitude_valid")),
        sa.CheckConstraint("last_longitude IS NULL OR last_longitude BETWEEN -180 AND 180", name=op.f("ck_delivery_route_last_longitude_valid")),
        sa.ForeignKeyConstraint(["demo_run_id"], ["demo_run.id"], name=op.f("fk_delivery_route_demo_run_id_demo_run"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["driver_id"], ["identity_user.id"], name=op.f("fk_delivery_route_driver_id_identity_user"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["supplier_order_id"], ["supplier_order.id"], name=op.f("fk_delivery_route_supplier_order_id_supplier_order"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_delivery_route")),
        sa.UniqueConstraint("supplier_order_id", name=op.f("uq_delivery_route_supplier_order_id")),
    )
    op.create_index(op.f("ix_delivery_route_demo_run_id"), "delivery_route", ["demo_run_id"])
    op.create_index(op.f("ix_delivery_route_driver_id"), "delivery_route", ["driver_id"])
    op.create_table(
        "driver_location_point",
        sa.Column("route_id", sa.Uuid(), nullable=False),
        sa.Column("driver_id", sa.Uuid(), nullable=False),
        sa.Column("demo_run_id", sa.Uuid(), nullable=False),
        sa.Column("latitude", sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column("longitude", sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column("accuracy_meters", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("latitude BETWEEN -90 AND 90", name=op.f("ck_driver_location_point_latitude_valid")),
        sa.CheckConstraint("longitude BETWEEN -180 AND 180", name=op.f("ck_driver_location_point_longitude_valid")),
        sa.CheckConstraint("accuracy_meters >= 0", name=op.f("ck_driver_location_point_accuracy_non_negative")),
        sa.ForeignKeyConstraint(["demo_run_id"], ["demo_run.id"], name=op.f("fk_driver_location_point_demo_run_id_demo_run"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["driver_id"], ["identity_user.id"], name=op.f("fk_driver_location_point_driver_id_identity_user"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["route_id"], ["delivery_route.id"], name=op.f("fk_driver_location_point_route_id_delivery_route"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_driver_location_point")),
    )
    op.create_index(op.f("ix_driver_location_point_demo_run_id"), "driver_location_point", ["demo_run_id"])
    op.create_index(op.f("ix_driver_location_point_driver_id"), "driver_location_point", ["driver_id"])
    op.create_index(op.f("ix_driver_location_point_route_id"), "driver_location_point", ["route_id"])
    op.create_index("ix_driver_location_point_route_recorded_at", "driver_location_point", ["route_id", "recorded_at"])


def downgrade() -> None:
    op.drop_index("ix_driver_location_point_route_recorded_at", table_name="driver_location_point")
    op.drop_index(op.f("ix_driver_location_point_route_id"), table_name="driver_location_point")
    op.drop_index(op.f("ix_driver_location_point_driver_id"), table_name="driver_location_point")
    op.drop_index(op.f("ix_driver_location_point_demo_run_id"), table_name="driver_location_point")
    op.drop_table("driver_location_point")
    op.drop_index(op.f("ix_delivery_route_driver_id"), table_name="delivery_route")
    op.drop_index(op.f("ix_delivery_route_demo_run_id"), table_name="delivery_route")
    op.drop_table("delivery_route")
