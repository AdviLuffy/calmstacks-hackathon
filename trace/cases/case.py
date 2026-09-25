"""Forensic case data model, evidence registry, and audit event logger."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping


@dataclass
class AuditEvent:
    """Tamper-evident record of an action performed during an investigation."""

    event_id: str
    timestamp_utc: str
    action: str  # e.g., "EVIDENCE_INGESTED", "FORENSIC_CARVE", "AI_ANALYSIS", "REPORT_GENERATED"
    actor: str  # e.g., "Investigator", "System"
    details: str
    target_hash: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "event_id": self.event_id,
            "timestamp_utc": self.timestamp_utc,
            "action": self.action,
            "actor": self.actor,
            "details": self.details,
            "target_hash": self.target_hash,
        }


@dataclass
class ForensicCase:
    """A formal digital forensics case containing evidence and recovery findings."""

    case_id: str
    title: str
    investigator: str
    created_utc: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    write_blocked: bool = False
    acquisition_method: str = "logical_copy"
    evidence_items: list[dict[str, Any]] = field(default_factory=list)
    audit_log: list[AuditEvent] = field(default_factory=list)

    def log_event(self, action: str, actor: str, details: str, target_hash: str = "") -> AuditEvent:
        """Append an immutable audit entry."""
        ev = AuditEvent(
            event_id=f"EVT-{len(self.audit_log) + 1:04d}",
            timestamp_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            action=action,
            actor=actor,
            details=details,
            target_hash=target_hash,
        )
        self.audit_log.append(ev)
        return ev

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "title": self.title,
            "investigator": self.investigator,
            "created_utc": self.created_utc,
            "write_blocked": self.write_blocked,
            "acquisition_method": self.acquisition_method,
            "evidence_items_count": len(self.evidence_items),
            "evidence_items": self.evidence_items,
            "audit_log": [e.to_dict() for e in self.audit_log],
        }
