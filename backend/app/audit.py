"""Audit trail: who asked what, how it was routed, which sensitive actions ran.

Banks must be able to reconstruct every automated decision, so every important
step of a chat request is written to the audit_log table with its trace id.
"""
import logging

from .db.models import AuditLog
from .db.session import db_session

log = logging.getLogger("smartbank.audit")


def audit(trace_id: str, event: str, details: dict | None = None, user_id: int | None = None) -> None:
    try:
        with db_session() as db:
            db.add(AuditLog(trace_id=trace_id or "-", event=event, details=details or {}, user_id=user_id))
    except Exception:  # auditing must never break the user's request
        log.exception("failed to write audit event %s", event)
