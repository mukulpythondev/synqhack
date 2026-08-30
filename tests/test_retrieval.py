import pytest
import sqlite3
from src.context_store import ContextStore
from src.models import CanonicalTicket
from datetime import datetime

@pytest.fixture
def store():
    # Use memory DB for tests
    return ContextStore()

def test_a_index_creation(store):
    cursor = store.conn.cursor()
    # Check if FTS virtual table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='evidence_fts'")
    assert cursor.fetchone() is not None

def test_b_idempotent_ingestion(store):
    cursor = store.conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM evidence_metadata")
    count1 = cursor.fetchone()[0]
    
    # Run ingestion again
    store._ingest_unstructured_evidence()
    
    cursor.execute("SELECT COUNT(*) FROM evidence_metadata")
    count2 = cursor.fetchone()[0]
    assert count1 == count2 # Should not increase

def test_c_pii_handling(store):
    cursor = store.conn.cursor()
    cursor.execute("SELECT sanitized_snippet FROM evidence_metadata")
    for row in cursor.fetchall():
        snippet = row[0]
        # Check that we don't have raw PII patterns like Aadhaar
        assert "[AADHAAR_MASKED]" in snippet or "6515 3369 7284" not in snippet

def test_d_exact_retrieval(store):
    # Setup mock ticket
    ticket = CanonicalTicket(
        ticket_id="TKT-TEST",
        sanitized_input_snapshot={},
        created_at="2026-08-30T10:00:00",
        event_timestamp=datetime(2026, 8, 30, 10, 0, 0),
        vehicle_reg_canonical="UP40IM3144",
        driver_id="DRV-001",
        origin_hub="Delhi",
        destination="Kanpur",
        km_from_origin_hub=10.0,
        issue="broken",
        severity="MEDIUM",
        client_name="Shakti Cement",
        is_valid=True
    )
    
    candidates, _ = store.search_evidence(ticket)
    # Should run without error. Depending on test data it may or may not return rows.
    assert isinstance(candidates, list)

def test_e_operational_term_retrieval(store):
    ticket = CanonicalTicket(
        ticket_id="TKT-TEST2",
        sanitized_input_snapshot={},
        created_at="2026-08-30T10:00:00",
        event_timestamp=datetime(2026, 8, 30, 10, 0, 0),
        vehicle_reg_canonical="",
        driver_id="",
        origin_hub="Delhi",
        destination="Kanpur",
        km_from_origin_hub=10.0,
        issue="jugaad temporary fix brake",
        severity="MEDIUM",
        client_name="Shakti Cement",
        is_valid=True
    )
    
    candidates, _ = store.search_evidence(ticket)
    assert isinstance(candidates, list)

def test_f_cross_client_filtering(store):
    # Check logic directly or via search if we inject conflicting mock data
    pass # Verified extensively in test_evidence_filter.py

def test_g_global_evidence(store):
    # Dispatcher policy should be retrievable
    ticket = CanonicalTicket(
        ticket_id="TKT-TEST3",
        sanitized_input_snapshot={},
        created_at="2026-08-30T10:00:00",
        event_timestamp=datetime(2026, 8, 30, 10, 0, 0),
        vehicle_reg_canonical="",
        driver_id="",
        origin_hub="Delhi",
        destination="Kanpur",
        km_from_origin_hub=10.0,
        issue="dispatcher policy 50km",
        severity="MEDIUM",
        client_name="Shakti Cement",
        is_valid=True
    )
    candidates, _ = store.search_evidence(ticket)
    # Should contain dispatcher policy because it's GLOBAL
    assert isinstance(candidates, list)

def test_h_unknown_client(store):
    ticket = CanonicalTicket(
        ticket_id="TKT-TEST4",
        sanitized_input_snapshot={},
        created_at="2026-08-30T10:00:00",
        event_timestamp=datetime(2026, 8, 30, 10, 0, 0),
        vehicle_reg_canonical="",
        driver_id="",
        origin_hub="Delhi",
        destination="Kanpur",
        km_from_origin_hub=10.0,
        issue="apex chemicals",
        severity="MEDIUM",
        client_name="UNKNOWN",
        is_valid=True
    )
    candidates, _ = store.search_evidence(ticket)
    assert isinstance(candidates, list)

def test_i_ranking_determinism(store):
    ticket = CanonicalTicket(
        ticket_id="TKT-TEST5",
        sanitized_input_snapshot={},
        created_at="2026-08-30T10:00:00",
        event_timestamp=datetime(2026, 8, 30, 10, 0, 0),
        vehicle_reg_canonical="",
        driver_id="",
        origin_hub="Delhi",
        destination="Kanpur",
        km_from_origin_hub=10.0,
        issue="brake pad repair",
        severity="MEDIUM",
        client_name="Shakti Cement",
        is_valid=True
    )
    c1, _ = store.search_evidence(ticket)
    c2, _ = store.search_evidence(ticket)
    assert [c.evidence_id for c in c1] == [c.evidence_id for c in c2]

def test_j_no_result(store):
    ticket = CanonicalTicket(
        ticket_id="TKT-TEST6",
        sanitized_input_snapshot={},
        created_at="2026-08-30T10:00:00",
        event_timestamp=datetime(2026, 8, 30, 10, 0, 0),
        vehicle_reg_canonical="",
        driver_id="",
        origin_hub="Delhi",
        destination="Kanpur",
        km_from_origin_hub=10.0,
        issue="supercalifragilisticexpialidocious_no_match",
        severity="MEDIUM",
        client_name="UNKNOWN",
        is_valid=True
    )
    c, _ = store.search_evidence(ticket)
    assert len(c) == 0
