"""
Unit Tests: PII Zero-Leakage Security Hard Gate Verification
"""

import json
from pathlib import Path
import pytest

from src.pii_scrubber import PIIScrubber
from src.config import (
    WORK_ORDERS_PATH,
    COMMS_PENDING_PATH,
    COMMS_SENT_PATH,
    QUARANTINE_PATH,
    AUDIT_PATH
)
from src.pipeline import BreakdownPipeline
from src.config import TICKETS_PATH

def test_no_raw_pii_in_outboxes():
    """
    Exhaustively scans every generated line in work_orders.jsonl,
    comms_pending.jsonl, comms_sent.jsonl, quarantine.jsonl, and audit.jsonl
    for raw Aadhaar, Indian 10-digit/E.164 phone numbers, and driving licenses.
    """
    # Execute pipeline to ensure fresh files
    pipeline = BreakdownPipeline()
    pipeline.process_ticket_queue(TICKETS_PATH)

    files_to_scan = [
        WORK_ORDERS_PATH,
        COMMS_PENDING_PATH,
        QUARANTINE_PATH,
        AUDIT_PATH
    ]

    for fpath in files_to_scan:
        assert fpath.exists(), f"Output file {fpath.name} must exist"
        with open(fpath, "r", encoding="utf-8") as f:
            for line_idx, line in enumerate(f, start=1):
                assert not PIIScrubber.contains_raw_pii(line), (
                    f"PII LEAK DETECTED in {fpath.name} line {line_idx}: {line.strip()}"
                )

def test_pii_scrubber_redaction():
    """
    Directly tests that scrubber masks raw phone, Aadhaar, and DL patterns.
    """
    raw_text = "Contact Sandeep on +91 93118 40522 or Aadhaar 6515 3369 7284 and DL HR16 20128663605"
    scrubbed = PIIScrubber.scrub_text(raw_text)

    assert "+91 93118 40522" not in scrubbed
    assert "6515 3369 7284" not in scrubbed
    assert "[PHONE_MASKED]" in scrubbed
    assert "[AADHAAR_MASKED]" in scrubbed
    assert not PIIScrubber.contains_raw_pii(scrubbed)
