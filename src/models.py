"""
Meridian Freight Breakdown Automation
Canonical Data Models & Standard Output Schemas
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import List, Dict, Any, Optional

@dataclass(frozen=True)
class CanonicalTicket:
    ticket_id: str
    sanitized_input_snapshot: Dict[str, Any]
    created_at: str                         # Immutable ISO-8601 string from source
    event_timestamp: datetime
    vehicle_reg_canonical: str             # Normalized plate (e.g. "UP40IM3144")
    driver_id: str                         # Strictly canonical driver ID (e.g. "DRV-020")
    origin_hub: str
    destination: str
    km_from_origin_hub: float
    issue: str
    severity: str
    client_name: str
    is_valid: bool
    quarantine_reason: Optional[str] = None

@dataclass(frozen=True)
class CanonicalVehicle:
    vehicle_id: str                        # e.g. "MF-068"
    registration_canonical: str            # e.g. "UP17GN7381"
    model: str
    year: int
    bs_stage: str                          # "BS4" | "BS6"
    has_engine_heater: bool
    home_hub: str
    capacity_tonnes: float
    status: str                            # "Active" | "Maintenance" | "Grounded"
    is_refrigerated: bool = True
    service_due_date: Optional[date] = None
    has_unaddressed_critical_fault: bool = False
    active_jugaad_date: Optional[date] = None
    jugaad_home_hub: Optional[str] = None
    last_brake_work_date: Optional[date] = None
    source_provenance: str = "fleet_master.csv"

@dataclass(frozen=True)
class CanonicalDriver:
    driver_id: str                         # Driver ID only (NO human names)
    joining_date: date
    home_hub: str
    source_provenance: str = "drivers_roster.csv"

@dataclass(frozen=True)
class CanonicalMaintenanceEvent:
    event_id: str
    vehicle_canonical: str
    event_date: date
    odometer_km: int
    mechanic_name: str
    is_brake_work: bool
    is_jugaad_temporary: bool
    is_permanent_repair_done: bool
    permanent_repair_date: Optional[date]
    sanitized_notes: str
    source_provenance: str

@dataclass(frozen=True)
class WorkOrderOutput:
    work_order_id: str
    ticket_id: str
    vehicle_reg: str                       # Assigned replacement vehicle registration
    created_at: str                        # Deterministic timestamp from source ticket
    citations: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "work_order_id": self.work_order_id,
            "ticket_id": self.ticket_id,
            "vehicle_reg": self.vehicle_reg,
            "created_at": self.created_at,
            "citations": self.citations
        }

@dataclass(frozen=True)
class CommsPendingOutput:
    draft_id: str
    ticket_id: str
    recipient: str
    proposed_body: str
    sla_type: str
    replacement_vehicle: str
    citations: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "draft_id": self.draft_id,
            "ticket_id": self.ticket_id,
            "recipient": self.recipient,
            "proposed_body": self.proposed_body,
            "sla_type": self.sla_type,
            "replacement_vehicle": self.replacement_vehicle,
            "citations": self.citations
        }

@dataclass(frozen=True)
class CommsSentOutput:
    message_id: str
    ticket_id: str
    recipient: str
    body: str
    approved_by: str
    sent_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "ticket_id": self.ticket_id,
            "recipient": self.recipient,
            "body": self.body,
            "approved_by": self.approved_by,
            "sent_at": self.sent_at
        }

@dataclass(frozen=True)
class QuarantineOutput:
    ticket_id: str
    sanitized_record: Dict[str, Any]
    reason_code: str
    quarantined_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticket_id": self.ticket_id,
            "sanitized_record": self.sanitized_record,
            "reason_code": self.reason_code,
            "quarantined_at": self.quarantined_at
        }

@dataclass(frozen=True)
class AuditEvent:
    event_id: str
    ticket_id: str
    step_number: int
    step_name: str
    decision: str
    input_data_summary: Dict[str, Any]
    rule_applied: str
    source_citations: List[str]
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "ticket_id": self.ticket_id,
            "step_number": self.step_number,
            "step_name": self.step_name,
            "decision": self.decision,
            "input_data_summary": self.input_data_summary,
            "rule_applied": self.rule_applied,
            "source_citations": self.source_citations,
            "timestamp": self.timestamp
        }
