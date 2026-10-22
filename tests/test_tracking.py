"""Rastreamento de rota: autorização, idempotência e última localização."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select, text

from rotalog.core.database import transactional_session
from rotalog.inventory.models import CapacitySlot, Warehouse
from rotalog.logistics.models import DeliveryRoute, DriverLocationPoint
from rotalog.ordering.models import CheckoutSession, Purchase, SupplierOrder


def _ok(response, status: int = 200):
    assert response.status_code == status, response.text
    return response.json() if response.content else None


def _login(client, alias: str):
    result = _ok(
        client.post(
            "/api/v1/auth/login",
            data={
                "username": f"{alias}@demo.rotalog.invalid",
                "password": "synthetic-test-password",
            },
        )
    )
    return {"Authorization": f"Bearer {result['access_token']}"}, result["user"]


def _ready_order(demo_client, supplier_user, buyer_user):
    """Cria só o mínimo de dados relacionais para a rota de teste."""

    factory = demo_client.app.state.session_factory
    supplier_organization_id = UUID(supplier_user["organization_id"])
    buyer_organization_id = UUID(buyer_user["organization_id"])
    demo_run_id = UUID(supplier_user["demo_run_id"])
    with transactional_session(factory) as session:
        warehouse = session.scalar(
            select(Warehouse).where(
                Warehouse.supplier_organization_id == supplier_organization_id,
                Warehouse.demo_run_id == demo_run_id,
            )
        )
        capacity = session.scalar(
            select(CapacitySlot).where(CapacitySlot.warehouse_id == warehouse.id)
        )
        checkout = CheckoutSession(
            buyer_organization_id=buyer_organization_id,
            supplier_organization_id=supplier_organization_id,
            warehouse_id=warehouse.id,
            capacity_slot_id=capacity.id,
            demo_run_id=demo_run_id,
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
        )
        session.add(checkout)
        session.flush()
        purchase = Purchase(
            checkout_id=checkout.id,
            buyer_organization_id=buyer_organization_id,
            demo_run_id=demo_run_id,
        )
        session.add(purchase)
        session.flush()
        order = SupplierOrder(
            purchase_id=purchase.id,
            buyer_organization_id=buyer_organization_id,
            supplier_organization_id=supplier_organization_id,
            warehouse_id=warehouse.id,
            demo_run_id=demo_run_id,
            state="READY_TO_DISPATCH",
            accepts_partial=False,
            acceptance_deadline=datetime.now(UTC) + timedelta(hours=24),
        )
        session.add(order)
        session.flush()
        return str(order.id), order.version


def test_driver_location_flow(demo_client):
    supplier, supplier_user = _login(demo_client, "fornecedor")
    driver, driver_user = _login(demo_client, "motorista")
    buyer, buyer_user = _login(demo_client, "comprador")
    order_id, order_version = _ready_order(demo_client, supplier_user, buyer_user)

    route = _ok(
        demo_client.post(
            f"/api/v1/supplier-orders/{order_id}/delivery-route",
            headers=supplier,
            json={
                "driver_id": driver_user["id"],
                "expected_version": order_version,
            },
        ),
        201,
    )
    assert _ok(demo_client.get("/api/v1/driver/delivery-routes", headers=driver))[0][
        "id"
    ] == route["id"]

    started = _ok(
        demo_client.post(
            f"/api/v1/driver/delivery-routes/{route['id']}/start",
            headers=driver,
            json={"expected_version": route["version"]},
        )
    )
    location_payload = {
        "latitude": "-3.119000",
        "longitude": "-60.021700",
        "accuracy_meters": "12.50",
        "recorded_at": datetime.now(UTC).isoformat(),
    }
    location_headers = driver | {"Idempotency-Key": "tracking-point-001"}
    saved = _ok(
        demo_client.post(
            f"/api/v1/driver/delivery-routes/{route['id']}/locations",
            headers=location_headers,
            json=location_payload,
        ),
        201,
    )
    assert (
        _ok(
            demo_client.post(
                f"/api/v1/driver/delivery-routes/{route['id']}/locations",
                headers=location_headers,
                json=location_payload,
            ),
            201,
        )
        == saved
    )
    latest = _ok(
        demo_client.get(f"/api/v1/delivery-routes/{route['id']}/location", headers=buyer)
    )
    assert latest["id"] == saved["id"]
    assert latest["latitude"] == "-3.119000"
    assert latest["is_stale"] is False

    factory = demo_client.app.state.session_factory
    with transactional_session(factory) as session:
        point_position = session.execute(
            select(
                func.ST_AsText(DriverLocationPoint.position),
                func.ST_SRID(DriverLocationPoint.position),
            ).where(DriverLocationPoint.id == UUID(saved["id"]))
        ).one()
        route_position = session.execute(
            select(
                func.ST_AsText(DeliveryRoute.last_position),
                func.ST_SRID(DeliveryRoute.last_position),
            ).where(DeliveryRoute.id == UUID(route["id"]))
        ).one()
        spatial_indexes = set(
            session.scalars(
                text(
                    """
                    SELECT index_class.relname
                    FROM pg_index
                    JOIN pg_class index_class ON index_class.oid = pg_index.indexrelid
                    JOIN pg_am ON pg_am.oid = index_class.relam
                    WHERE pg_am.amname = 'gist'
                      AND index_class.relname IN (
                        'ix_driver_location_point_position',
                        'ix_delivery_route_last_position'
                      )
                    """
                )
            )
        )
    assert point_position == ("POINT(-60.0217 -3.119)", 4326)
    assert route_position == ("POINT(-60.0217 -3.119)", 4326)
    assert spatial_indexes == {
        "ix_driver_location_point_position",
        "ix_delivery_route_last_position",
    }

    route_after_point = _ok(
        demo_client.get("/api/v1/driver/delivery-routes", headers=driver)
    )[0]
    completed = _ok(
        demo_client.post(
            f"/api/v1/driver/delivery-routes/{route['id']}/complete",
            headers=driver,
            json={"expected_version": route_after_point["version"]},
        )
    )
    assert completed["state"] == "COMPLETED"
    assert (
        demo_client.post(
            f"/api/v1/driver/delivery-routes/{route['id']}/locations",
            headers=driver | {"Idempotency-Key": "tracking-point-002"},
            json=location_payload,
        ).status_code
        == 409
    )
