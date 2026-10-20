"""Expiração local de reservas. Sem despacho, entrega ou integrações reais."""

import time

from rotalog.core.config import get_settings
from rotalog.core.database import create_database_engine, create_session_factory
from rotalog.identity.security import require_demo
from rotalog.ordering.service import expire_checkouts, expire_orders


def main() -> None:
    settings = get_settings()
    require_demo(settings)
    engine = create_database_engine(settings.database_url.get_secret_value())
    try:
        while True:
            expire_checkouts(create_session_factory(engine))
            expire_orders(create_session_factory(engine))
            time.sleep(10)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
