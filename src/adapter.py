"""
Meridian Freight Breakdown Automation
Dynamic Schema Adapter for Surprise & Mutated Ticket Files
"""

from typing import Dict, Any, Optional, Tuple
from src.normalizer import (
    normalize_vehicle_reg,
    normalize_client_name,
    normalize_hub_name,
    parse_iso_datetime
)
from src.pii_scrubber import PIIScrubber
from src.models import CanonicalTicket

class DynamicTicketAdapter:
    """
    Tolerates schema drifts, renamed columns, format mutations, and nested structures.
    Converts arbitrary incoming ticket records into CanonicalTicket or quarantine states.
    """

    KEY_ALIASES = {
        "ticket_id": ["ticket_id", "id", "ticket_number", "tkt_id", "ticket_no", "t_id"],
        "vehicle": ["vehicle", "truck_no", "reg_no", "vehicle_reg", "plate", "vehicle_number", "registration"],
        "driver_id": ["driver_id", "driver_code", "driver", "drv_id", "emp_id"],
        "origin_hub": ["origin_hub", "origin", "from_hub", "start_hub", "source_hub", "source"],
        "destination": ["destination", "dest", "to_hub", "target_hub", "target"],
        "km_from_origin_hub": ["km_from_origin_hub", "km_from_origin", "distance_km", "breakdown_km", "km"],
        "issue": ["issue", "fault", "problem", "breakdown_reason", "description", "details"],
        "severity": ["severity", "priority", "level", "urgency"],
        "client": ["client", "customer", "account", "client_name"],
        "created_at": ["created_at", "timestamp", "time", "date", "created_date", "datetime"]
    }

    @classmethod
    def adapt_record(cls, raw_record: Dict[str, Any]) -> CanonicalTicket:
        """
        Parses and validates a single raw ticket record.
        Returns a CanonicalTicket with is_valid=True/False and quarantine reason if invalid.
        """
        # 1. Scrub PII immediately at ingestion boundary
        sanitized_input = PIIScrubber.scrub_dict(raw_record)

        # 2. Extract keys using alias mapping
        extracted = {}
        for canonical_key, aliases in cls.KEY_ALIASES.items():
            val = None
            for alias in aliases:
                if alias in raw_record and raw_record[alias] is not None:
                    val = raw_record[alias]
                    break
            extracted[canonical_key] = val

        ticket_id = str(extracted.get("ticket_id") or "").strip()
        raw_vehicle = extracted.get("vehicle")
        raw_driver = extracted.get("driver_id")
        raw_origin = extracted.get("origin_hub")
        raw_dest = extracted.get("destination")
        raw_km = extracted.get("km_from_origin_hub")
        raw_issue = str(extracted.get("issue") or "").strip()
        raw_sev = str(extracted.get("severity") or "MEDIUM").strip().upper()
        raw_client = extracted.get("client")
        raw_created = extracted.get("created_at")

        # Validation Checks
        if not ticket_id:
            return CanonicalTicket(
                ticket_id="UNKNOWN_ID",
                sanitized_input_snapshot=sanitized_input,
                created_at="2026-08-30T00:00:00Z",
                event_timestamp=parse_iso_datetime("2026-08-30T00:00:00Z")[0],
                vehicle_reg_canonical="",
                driver_id="",
                origin_hub="",
                destination="",
                km_from_origin_hub=0.0,
                issue=raw_issue,
                severity=raw_sev,
                client_name="",
                is_valid=False,
                quarantine_reason="MISSING_CRITICAL_FIELDS (Missing ticket_id)"
            )

        # Parse Datetime
        event_dt, date_err = parse_iso_datetime(str(raw_created) if raw_created else None)
        if date_err or not event_dt:
            return CanonicalTicket(
                ticket_id=ticket_id,
                sanitized_input_snapshot=sanitized_input,
                created_at=str(raw_created or "INVALID_DATE"),
                event_timestamp=parse_iso_datetime("2026-08-30T00:00:00Z")[0],
                vehicle_reg_canonical="",
                driver_id=str(raw_driver or ""),
                origin_hub=str(raw_origin or ""),
                destination=str(raw_dest or ""),
                km_from_origin_hub=0.0,
                issue=raw_issue,
                severity=raw_sev,
                client_name=str(raw_client or ""),
                is_valid=False,
                quarantine_reason=f"INVALID_DATE_FORMAT ({date_err})"
            )

        # Normalize Vehicle Registration
        canon_reg, is_valid_plate = normalize_vehicle_reg(str(raw_vehicle) if raw_vehicle else None)
        if not is_valid_plate:
            return CanonicalTicket(
                ticket_id=ticket_id,
                sanitized_input_snapshot=sanitized_input,
                created_at=str(raw_created),
                event_timestamp=event_dt,
                vehicle_reg_canonical=canon_reg,
                driver_id=str(raw_driver or ""),
                origin_hub=str(raw_origin or ""),
                destination=str(raw_dest or ""),
                km_from_origin_hub=0.0,
                issue=raw_issue,
                severity=raw_sev,
                client_name=str(raw_client or ""),
                is_valid=False,
                quarantine_reason=f"UNRESOLVED_VEHICLE (Invalid registration '{raw_vehicle}')"
            )

        # Validate Critical Fields
        driver_id = str(raw_driver or "").strip()
        if not driver_id or not driver_id.startswith("DRV-"):
            return CanonicalTicket(
                ticket_id=ticket_id,
                sanitized_input_snapshot=sanitized_input,
                created_at=str(raw_created),
                event_timestamp=event_dt,
                vehicle_reg_canonical=canon_reg,
                driver_id=driver_id,
                origin_hub=str(raw_origin or ""),
                destination=str(raw_dest or ""),
                km_from_origin_hub=0.0,
                issue=raw_issue,
                severity=raw_sev,
                client_name=str(raw_client or ""),
                is_valid=False,
                quarantine_reason="MISSING_CRITICAL_FIELDS (Missing or invalid driver_id)"
            )

        origin_hub = normalize_hub_name(str(raw_origin) if raw_origin else None)
        dest_hub = normalize_hub_name(str(raw_dest) if raw_dest else None)

        if not origin_hub or not dest_hub:
            return CanonicalTicket(
                ticket_id=ticket_id,
                sanitized_input_snapshot=sanitized_input,
                created_at=str(raw_created),
                event_timestamp=event_dt,
                vehicle_reg_canonical=canon_reg,
                driver_id=driver_id,
                origin_hub=str(raw_origin or ""),
                destination=str(raw_dest or ""),
                km_from_origin_hub=0.0,
                issue=raw_issue,
                severity=raw_sev,
                client_name=str(raw_client or ""),
                is_valid=False,
                quarantine_reason="MISSING_CRITICAL_FIELDS (Missing or unresolved origin/destination hub)"
            )

        if raw_km is None:
            return CanonicalTicket(
                ticket_id=ticket_id,
                sanitized_input_snapshot=sanitized_input,
                created_at=str(raw_created),
                event_timestamp=event_dt,
                vehicle_reg_canonical=canon_reg,
                driver_id=driver_id,
                origin_hub=origin_hub,
                destination=dest_hub,
                km_from_origin_hub=0.0,
                issue=raw_issue,
                severity=raw_sev,
                client_name=str(raw_client or ""),
                is_valid=False,
                quarantine_reason="NULL_DISTANCE_METRIC (km_from_origin_hub is null)"
            )

        try:
            km_val = float(raw_km)
        except ValueError:
            return CanonicalTicket(
                ticket_id=ticket_id,
                sanitized_input_snapshot=sanitized_input,
                created_at=str(raw_created),
                event_timestamp=event_dt,
                vehicle_reg_canonical=canon_reg,
                driver_id=driver_id,
                origin_hub=origin_hub,
                destination=dest_hub,
                km_from_origin_hub=0.0,
                issue=raw_issue,
                severity=raw_sev,
                client_name=str(raw_client or ""),
                is_valid=False,
                quarantine_reason=f"NULL_DISTANCE_METRIC (Non-numeric distance '{raw_km}')"
            )

        client_name, client_state = normalize_client_name(str(raw_client) if raw_client else None)

        return CanonicalTicket(
            ticket_id=ticket_id,
            sanitized_input_snapshot=sanitized_input,
            created_at=str(raw_created),
            event_timestamp=event_dt,
            vehicle_reg_canonical=canon_reg,
            driver_id=driver_id,
            origin_hub=origin_hub,
            destination=dest_hub,
            km_from_origin_hub=km_val,
            issue=raw_issue,
            severity=raw_sev,
            client_name=client_name,
            is_valid=True,
            quarantine_reason=None
        )
