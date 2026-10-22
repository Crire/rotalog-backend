"""Armazena posições de rastreamento como pontos geográficos WGS 84."""

from alembic import op


revision = "20261022_0006"
down_revision = "20261022_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A extensão é compartilhada pelo banco, portanto nunca é removida no downgrade.
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    # Qualificar o tipo torna a migration independente do search_path da sessão.
    op.execute(
        "ALTER TABLE delivery_route ADD COLUMN last_position public.geography(POINT,4326)"
    )
    op.execute(
        "ALTER TABLE driver_location_point ADD COLUMN position public.geography(POINT,4326)"
    )

    # Preserve o histórico numérico e preencha o novo formato sem supor dados válidos.
    op.execute(
        """
        UPDATE delivery_route
        SET last_position = public.ST_SetSRID(public.ST_MakePoint(last_longitude, last_latitude), 4326)::public.geography
        WHERE last_latitude IS NOT NULL AND last_longitude IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE driver_location_point
        SET position = public.ST_SetSRID(public.ST_MakePoint(longitude, latitude), 4326)::public.geography
        WHERE position IS NULL
        """
    )
    op.execute("ALTER TABLE driver_location_point ALTER COLUMN position SET NOT NULL")

    op.create_index(
        "ix_delivery_route_last_position",
        "delivery_route",
        ["last_position"],
        postgresql_using="gist",
    )
    op.create_index(
        "ix_driver_location_point_position",
        "driver_location_point",
        ["position"],
        postgresql_using="gist",
    )


def downgrade() -> None:
    op.drop_index("ix_driver_location_point_position", table_name="driver_location_point")
    op.drop_index("ix_delivery_route_last_position", table_name="delivery_route")
    op.drop_column("driver_location_point", "position")
    op.drop_column("delivery_route", "last_position")
