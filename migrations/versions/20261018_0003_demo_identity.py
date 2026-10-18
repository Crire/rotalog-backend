"""Identidade, bloqueio de login e rastreabilidade do dataset sintético.

Revision ID: 20261018_0003
Revises: 20261013_0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261018_0003"
down_revision: str | None = "20261013_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _identity_columns() -> list[sa.Column]:
    return [
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "demo_run",
        *_identity_columns(),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_demo_run"),
        sa.UniqueConstraint("name", name="uq_demo_run_name"),
    )
    op.create_table(
        "organization",
        *_identity_columns(),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("demo_run_id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_organization"),
        sa.ForeignKeyConstraint(
            ["demo_run_id"],
            ["demo_run.id"],
            ondelete="RESTRICT",
            name="fk_organization_demo_run_id_demo_run",
        ),
    )
    op.create_index("ix_organization_demo_run_id", "organization", ["demo_run_id"])
    op.create_table(
        "identity_user",
        *_identity_columns(),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("demo_run_id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_identity_user"),
        sa.UniqueConstraint("email", name="uq_identity_user_email"),
        sa.CheckConstraint(
            "role IN ('comprador', 'fornecedor', 'motorista')",
            name=op.f("ck_identity_user_role_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organization.id"],
            ondelete="RESTRICT",
            name="fk_identity_user_organization_id_organization",
        ),
        sa.ForeignKeyConstraint(
            ["demo_run_id"],
            ["demo_run.id"],
            ondelete="RESTRICT",
            name="fk_identity_user_demo_run_id_demo_run",
        ),
    )
    for column in ("organization_id", "demo_run_id"):
        op.create_index(f"ix_identity_user_{column}", "identity_user", [column])
    op.create_table(
        "login_throttle",
        sa.Column("identifier", sa.String(64), nullable=False),
        sa.Column("failures", sa.Integer(), server_default="0", nullable=False),
        sa.Column("blocked_until", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("identifier", name="pk_login_throttle"),
        sa.CheckConstraint(
            "failures >= 0", name=op.f("ck_login_throttle_failures_non_negative")
        ),
    )
    # Nullable preserva os dados anteriores à introdução da demonstração.
    for table in ("product", "offer", "inventory_balance"):
        op.add_column(table, sa.Column("demo_run_id", sa.Uuid(), nullable=True))
        op.create_foreign_key(
            f"fk_{table}_demo_run_id_demo_run",
            table,
            "demo_run",
            ["demo_run_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        op.create_index(f"ix_{table}_demo_run_id", table, ["demo_run_id"])


def downgrade() -> None:
    for table in ("inventory_balance", "offer", "product"):
        op.drop_index(f"ix_{table}_demo_run_id", table_name=table)
        op.drop_constraint(
            f"fk_{table}_demo_run_id_demo_run", table, type_="foreignkey"
        )
        op.drop_column(table, "demo_run_id")
    op.drop_table("login_throttle")
    op.drop_table("identity_user")
    op.drop_table("organization")
    op.drop_table("demo_run")
