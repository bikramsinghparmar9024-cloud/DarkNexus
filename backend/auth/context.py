"""
Request Actor Context.

Chain of custody needs to record who did something, not merely that it
happened. "Record 47 was accessed" is far weaker in court than "Investigator
PB-CID-8821 accessed record 47 at 14:22".

The audit logger already accepted a user_id, but no caller passed one, because
none of them had access to the authenticated identity. Threading it through
thirty call sites would be noisy and easy to forget on the next one.

Instead the authenticated actor is placed in a context variable by middleware
at the start of each request. record_audit_event() reads it by default, so
every existing audit call becomes attributed without being modified, and a new
one is attributed automatically.

Context variables are safe here: each request runs in its own asyncio task,
and a ContextVar is isolated per task rather than shared across them.
"""

from contextvars import ContextVar
from typing import Any, Dict, Optional

# None outside a request - background jobs and the scheduler have no actor.
_current_actor: ContextVar[Optional[Dict[str, Any]]] = ContextVar(
    "current_actor", default=None)


def set_current_actor(actor: Optional[Dict[str, Any]]) -> Any:
    """Record the authenticated actor for this request. Returns a reset token."""
    return _current_actor.set(actor)


def reset_current_actor(token: Any) -> None:
    try:
        _current_actor.reset(token)
    except (ValueError, LookupError):
        # The context ended in a different task than it began; nothing to undo.
        pass


def get_current_actor() -> Optional[Dict[str, Any]]:
    """The authenticated actor for this request, or None."""
    return _current_actor.get()


def describe_actor() -> str:
    """Human-readable actor for audit detail text."""
    actor = get_current_actor()
    if not actor:
        return "system"
    username = actor.get("username") or "unknown"
    role = actor.get("role")
    return f"{username} ({role})" if role else username
