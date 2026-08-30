"""
Unit Tests: Idempotency, Deduplication, and Deterministic Re-runs
"""

import json
import subprocess
import sys
import hashlib
from pathlib import Path
import pytest

from src.config import (
    WORK_ORDERS_PATH,
    COMMS_PENDING_PATH,
    COMMS_SENT_PATH,
    QUARANTINE_PATH,
    AUDIT_PATH,
    TICKETS_PATH
)
from src.pipeline import BreakdownPipeline

def test_deduplication_in_queue():
    """
    Validates that duplicate ticket IDs in tickets.json (TKT-0009, TKT-0020, TKT-0024)
    are processed exactly once, generating exactly 1 work order and 1 pending comms entry.
    """
    pipeline = BreakdownPipeline()
    work_orders, pending_comms, quarantine, audit = pipeline.process_ticket_queue(TICKETS_PATH)

    # 35 raw tickets = 30 valid unique + 3 duplicates + 2 malformed
    assert len(work_orders) == 30
    assert len(pending_comms) == 30
    assert len(quarantine) == 2

    # Check that duplicate ticket IDs appear exactly once in work orders
    wo_ticket_ids = [wo.ticket_id for wo in work_orders]
    assert len(wo_ticket_ids) == len(set(wo_ticket_ids))
    assert wo_ticket_ids.count("TKT-0009") == 1
    assert wo_ticket_ids.count("TKT-0020") == 1
    assert wo_ticket_ids.count("TKT-0024") == 1

def test_bit_for_bit_rerun_identity():
    """
    Validates that running the entire pipeline twice produces identical SHA-256 hashes
    across all output and audit files.
    """
    files_to_hash = [
        WORK_ORDERS_PATH,
        COMMS_PENDING_PATH,
        COMMS_SENT_PATH,
        QUARANTINE_PATH,
        AUDIT_PATH
    ]

    # Run 1
    subprocess.run([sys.executable, "run_pipeline.py", "--eval-mode"], check=True)
    hashes_run1 = {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in files_to_hash if f.exists()}

    # Run 2 (Consecutive)
    subprocess.run([sys.executable, "run_pipeline.py", "--eval-mode"], check=True)
    hashes_run2 = {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in files_to_hash if f.exists()}

    assert hashes_run1 == hashes_run2
    for fname in hashes_run1:
        assert hashes_run1[fname] == hashes_run2[fname], f"Mismatch in {fname} after rerun"
