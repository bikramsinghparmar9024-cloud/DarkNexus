"""
Audit Log & Chain of Custody Logger.
Maintains tamper-evident records of every action taken by investigators
(e.g., viewing records, running scrapers, exporting PDF dossiers) for court submission.
"""

from typing import Optional
from datetime import datetime
import logging
from database.postgres import AsyncSessionLocal, AuditLog

logger = logging.getLogger("audit_log")


async def record_audit_event(
    action: str,
    user_id: Optional[int] = None,
    resource: Optional[str] = None,
    ip_address: Optional[str] = None,
    details: Optional[str] = None
):
    """
    Save an audit entry.

    user_id and ip_address default to the authenticated actor for the current
    request, so callers do not have to thread identity through by hand and
    cannot forget to.
    """
    from auth.context import get_current_actor, describe_actor

    actor = get_current_actor()
    if actor:
        if user_id is None:
            user_id = actor.get("user_id")
        if ip_address is None:
            ip_address = actor.get("ip_address")
        actor_label = describe_actor()
        details = f"[{actor_label}] {details}" if details else f"Performed by {actor_label}"

    try:
        async with AsyncSessionLocal() as session:
            entry = AuditLog(
                user_id=user_id,
                action=action,
                resource=resource,
                ip_address=ip_address,
                timestamp=datetime.utcnow(),
                details=details
            )
            session.add(entry)
            await session.commit()
            logger.info(f"Audit event recorded: [{action}] by user {user_id} on {resource}")
    except Exception as e:
        logger.error(f"Failed to record audit event: {e}")
