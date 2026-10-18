"""Validação pública da execução sintética dentro de cada transação de escrita."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from rotalog.core.errors import RotaLogError
from rotalog.demo.fixtures import DEMO_RUN_ID
from rotalog.demo.models import DemoRun


def require_active_run(session: Session, run_id: UUID = DEMO_RUN_ID) -> UUID:
    """Mantém a execução ativa até o commit, sem serializar escritas independentes."""
    active_id = session.scalar(
        select(DemoRun.id)
        .where(DemoRun.id == run_id, DemoRun.is_active.is_(True))
        .with_for_update(read=True)
    )
    if active_id is None:
        raise RotaLogError(
            code="DEMO_UNAVAILABLE",
            message="Execução sintética indisponível. Inicialize a demo com o seed.",
            status_code=409,
        )
    return active_id
