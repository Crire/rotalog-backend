import hashlib
import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from rotalog.core.contracts import fail
from rotalog.identity.schemas import UserResponse
from rotalog.operations.models import IdempotencyRecord


def begin_idempotency(
    session: Session, actor: UserResponse, operation: str, key: str, payload: dict
) -> tuple[dict | None, str]:
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    lock_id = int.from_bytes(
        hashlib.sha256(f"{actor.organization_id}:{operation}:{key}".encode()).digest()[
            :8
        ],
        signed=True,
    )
    session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_id})
    existing = session.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.organization_id == actor.organization_id,
            IdempotencyRecord.operation == operation,
            IdempotencyRecord.key == key,
        )
    )
    if existing:
        if existing.payload_hash != digest:
            fail("IDEMPOTENCY_KEY_REUSED", "Chave já usada com outro conteúdo.")
        return existing.response, digest
    return None, digest


def finish_idempotency(
    session: Session,
    actor: UserResponse,
    operation: str,
    key: str,
    digest: str,
    response: dict,
) -> dict:
    session.add(
        IdempotencyRecord(
            organization_id=actor.organization_id,
            operation=operation,
            key=key,
            payload_hash=digest,
            response=response,
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )
    )
    return response
