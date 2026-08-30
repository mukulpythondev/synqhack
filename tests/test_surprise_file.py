"""
Unit Tests: Dynamic Surprise Ticket File Adaptation & Schema Drift Handling
"""

import json
import tempfile
from pathlib import Path
import pytest

from src.pipeline import BreakdownPipeline

def test_surprise_file_with_mutated_keys():
    """
    Simulates a surprise final-hour ticket file with renamed keys:
    'truck_no' -> 'vehicle'
    'driver_code' -> 'driver_id'
    'from_hub' -> 'origin_hub'
    'to_hub' -> 'destination'
    'distance_km' -> 'km_from_origin_hub'
    'fault' -> 'issue'
    """
    mutated_tickets = [
        {
            "id": "TKT-SURPRISE-01",
            "date": "2026-08-30T10:00:00",
            "truck_no": "UP-40-IM-3144",
            "driver_code": "DRV-020",
            "from_hub": "Lucknow",
            "distance_km": 15.0,
            "to_hub": "Lucknow",
            "fault": "fuel line leak",
            "priority": "HIGH",
            "customer": "Shakti Cement"
        },
        {
            # Malformed surprise ticket missing keys
            "id": "TKT-SURPRISE-BAD",
            "date": "2026-08-30T10:00:00",
            "truck_no": "unknown_truck"
        }
    ]

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tf:
        json.dump(mutated_tickets, tf)
        tmp_path = Path(tf.name)

    try:
        pipeline = BreakdownPipeline()
        work_orders, pending_comms, quarantine, audit = pipeline.process_ticket_queue(tmp_path)

        assert len(work_orders) == 1
        assert work_orders[0].ticket_id == "TKT-SURPRISE-01"
        assert len(quarantine) == 1
        assert quarantine[0].ticket_id == "TKT-SURPRISE-BAD"
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
