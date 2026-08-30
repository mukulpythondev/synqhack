"""
Unit Tests: Quarantine Manager and Malformed Record Handling
"""

import json
from pathlib import Path
import pytest

from src.models import CanonicalTicket
from src.adapter import DynamicTicketAdapter
from src.pipeline import BreakdownPipeline
from src.config import TICKETS_PATH, QUARANTINE_PATH

def test_quarantined_tickets_in_queue():
    """
    Validates that TKT-9101 and TKT-9102 are properly quarantined
    with accurate reason codes and zero unhandled exceptions.
    """
    pipeline = BreakdownPipeline()
    work_orders, pending_comms, quarantine, audit = pipeline.process_ticket_queue(TICKETS_PATH)

    quarantined_ids = [q.ticket_id for q in quarantine]
    assert "TKT-9101" in quarantined_ids
    assert "TKT-9102" in quarantined_ids

    # Check reason codes
    q_map = {q.ticket_id: q for q in quarantine}
    assert any(k in q_map["TKT-9101"].reason_code for k in ["MISSING_CRITICAL_FIELDS", "NULL_DISTANCE_METRIC", "UNRESOLVED_VEHICLE"])
    assert any(k in q_map["TKT-9102"].reason_code for k in ["INVALID_DATE_FORMAT", "UNRESOLVED_VEHICLE", "MISSING_CRITICAL_FIELDS"])

def test_dynamic_adapter_edge_cases():
    """
    Tests edge-case malformations in individual records.
    """
    # 1. Missing ticket_id
    t1 = DynamicTicketAdapter.adapt_record({"vehicle": "UP40IM3144", "driver_id": "DRV-001"})
    assert t1.is_valid is False
    assert "Missing ticket_id" in t1.quarantine_reason

    # 2. Corrupted plate
    t2 = DynamicTicketAdapter.adapt_record({
        "ticket_id": "TKT-TEST-01",
        "vehicle": "XX??9999",
        "driver_id": "DRV-001",
        "created_at": "2026-08-30T10:00:00",
        "origin_hub": "Delhi",
        "destination": "Kanpur",
        "km_from_origin_hub": 25.0
    })
    assert t2.is_valid is False
    assert "UNRESOLVED_VEHICLE" in t2.quarantine_reason

def test_unknown_client_quarantine(tmp_path):
    """
    Validates that an unregistered client with no verified SLA contract
    is quarantined with INSUFFICIENT_DATA and does not generate ungrounded work orders.
    """
    unknown_ticket = [{
        "ticket_id": "TKT-SYN-UNKNOWN-CLIENT",
        "vehicle": "UP40IM3144",
        "driver_id": "DRV-001",
        "origin_hub": "Lucknow",
        "destination": "Delhi",
        "km_from_origin_hub": 20.0,
        "issue": "engine overheating",
        "severity": "HIGH",
        "client": "Acme Unknown Corp",
        "created_at": "2026-08-30T10:00:00"
    }]
    tkt_file = tmp_path / "unknown_client.json"
    tkt_file.write_text(json.dumps(unknown_ticket), encoding="utf-8")

    pipeline = BreakdownPipeline()
    wos, comms, quarantine, audit = pipeline.process_ticket_queue(tkt_file)

    assert len(wos) == 0
    assert len(comms) == 0
    assert len(quarantine) == 1
    assert "INSUFFICIENT_DATA" in quarantine[0].reason_code
    assert "Acme Unknown Corp" in quarantine[0].reason_code

