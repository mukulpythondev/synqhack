import pytest
from src.pipeline import BreakdownPipeline
import os
import json

@pytest.fixture
def test_pipeline():
    # Setup test pipeline with some mock data if necessary
    os.environ["GEMINI_ENABLED"] = "true"
    os.environ["GEMINI_API_KEY"] = "fake-key-for-test"
    pipeline = BreakdownPipeline()
    return pipeline

def test_gemini_proposes_nonexistent_vehicle(test_pipeline, monkeypatch, tmp_path):
    # Mock Gemini to return a fake vehicle
    from src.llm_adapter import PerceptionFacts
    monkeypatch.setattr("src.llm_adapter.PerceptionRouter.extract_facts", lambda self, text, context_source="": (
        PerceptionFacts(
            confidence=0.9,
            vehicle_reg="XX99XX9999" # Non-existent
        ),
        "Mock"
    ))
    
    # We must mock store.search_evidence to return SOME evidence so it gets past the corroboration check
    from src.models import EvidenceCandidate
    monkeypatch.setattr("src.context_store.ContextStore.search_evidence", lambda self, ticket, limit=10: (
        [EvidenceCandidate(
            evidence_id="1", source_file="dummy.txt", thread_id="t1",
            timestamp="2026-08-30T00:00:00Z", sanitized_snippet="dummy",
            retrieval_method="FTS5", retrieval_rank=-1.0, source_scope="GLOBAL",
            detected_client=None, detected_vehicle=None
        )],
        []
    ))

    raw_ticket = {
        "ticket_id": "TKT-FALLBACK-01",
        "client_name": "Apex Chemicals",
        "fault": "kal raat wali gaadi broke down",
        "created_at": "2026-08-30T10:00:00Z"
    }

    test_file = tmp_path / "temp.json"
    with open(test_file, "w") as f:
        json.dump([raw_ticket], f)
    work_orders, comms, quarantine, audit = test_pipeline.process_ticket_queue(test_file)
    
    assert len(quarantine) > 0
    q_record = quarantine[-1]
    assert "TKT-FALLBACK-01" in q_record.ticket_id
    assert "CONTEXT_UNCERTAIN/AMBIGUOUS_ENTITY" in q_record.reason_code
    assert "non-existent vehicle" in q_record.reason_code

def test_gemini_proposes_existing_vehicle_without_corroboration(test_pipeline, monkeypatch, tmp_path):
    from src.llm_adapter import PerceptionFacts
    monkeypatch.setattr("src.llm_adapter.PerceptionRouter.extract_facts", lambda self, text, context_source="": (
        PerceptionFacts(
            confidence=0.9,
            vehicle_reg="DL30JD1420" # Real vehicle in fleet
        ),
        "Mock"
    ))
    
    # Return NO corroborating evidence
    monkeypatch.setattr("src.context_store.ContextStore.search_evidence", lambda self, ticket, limit=10: ([], []))

    raw_ticket = {
        "ticket_id": "TKT-FALLBACK-02",
        "client_name": "Apex Chemicals",
        "fault": "kal raat wali gaadi broke down",
        "created_at": "2026-08-30T10:00:00Z"
    }

    test_file = tmp_path / "temp.json"
    with open(test_file, "w") as f:
        json.dump([raw_ticket], f)
    work_orders, comms, quarantine, audit = test_pipeline.process_ticket_queue(test_file)
    
    assert len(quarantine) > 0
    q_record = quarantine[-1]
    assert "TKT-FALLBACK-02" in q_record.ticket_id
    assert "CONTEXT_UNCERTAIN/AMBIGUOUS_ENTITY" in q_record.reason_code
    assert "no corroborating evidence found" in q_record.reason_code

def test_gemini_proposes_existing_vehicle_with_corroboration(test_pipeline, monkeypatch, tmp_path):
    from src.llm_adapter import PerceptionFacts
    monkeypatch.setattr("src.llm_adapter.PerceptionRouter.extract_facts", lambda self, text, context_source="": (
        PerceptionFacts(
            confidence=0.9,
            vehicle_reg="DL30JD1420" # Real vehicle
        ),
        "Mock"
    ))
    
    from src.models import EvidenceCandidate
    monkeypatch.setattr("src.context_store.ContextStore.search_evidence", lambda self, ticket, limit=10: (
        [EvidenceCandidate(
            evidence_id="1", source_file="dummy.txt", thread_id="t1",
            timestamp="2026-08-30T00:00:00Z", sanitized_snippet="dummy",
            retrieval_method="FTS5", retrieval_rank=-1.0, source_scope="GLOBAL",
            detected_client=None, detected_vehicle=None
        )],
        []
    ))

    raw_ticket = {
        "ticket_id": "TKT-FALLBACK-03",
        "client_name": "Apex Chemicals",
        "fault": "kal raat wali gaadi broke down",
        "origin_hub": "Delhi",
        "destination": "Kanpur",
        "created_at": "2026-08-30T10:00:00Z"
    }

    test_file = tmp_path / "temp.json"
    with open(test_file, "w") as f:
        json.dump([raw_ticket], f)
    work_orders, comms, quarantine, audit = test_pipeline.process_ticket_queue(test_file)
    
    # Should result in a work order!
    found_wo = False
    for wo in work_orders:
        if wo.ticket_id == "TKT-FALLBACK-03":
            found_wo = True
            break
    assert found_wo

def test_gemini_unavailable(test_pipeline, monkeypatch, tmp_path):
    # Simulate API failure / timeout
    from src.llm_adapter import PerceptionFacts
    monkeypatch.setattr("src.llm_adapter.PerceptionRouter.extract_facts", lambda self, text, context_source="": (
        PerceptionFacts(confidence=0.0), # Low confidence
        "Mock"
    ))
    
    monkeypatch.setattr("src.context_store.ContextStore.search_evidence", lambda self, ticket, limit=10: ([], []))

    raw_ticket = {
        "ticket_id": "TKT-FALLBACK-04",
        "client_name": "Apex Chemicals",
        "fault": "kal raat wali gaadi broke down",
        "created_at": "2026-08-30T10:00:00Z"
    }

    test_file = tmp_path / "temp.json"
    with open(test_file, "w") as f:
        json.dump([raw_ticket], f)
    work_orders, comms, quarantine, audit = test_pipeline.process_ticket_queue(test_file)
    
    assert len(quarantine) > 0
    q_record = quarantine[-1]
    assert "TKT-FALLBACK-04" in q_record.ticket_id
    assert "CONTEXT_UNCERTAIN/AMBIGUOUS_ENTITY" in q_record.reason_code
    assert "could not confidently extract vehicle" in q_record.reason_code

def test_cross_client_evidence_rejected(test_pipeline, monkeypatch, tmp_path):
    from src.llm_adapter import PerceptionFacts
    monkeypatch.setattr("src.llm_adapter.PerceptionRouter.extract_facts", lambda self, text, context_source="": (
        PerceptionFacts(
            confidence=0.9,
            vehicle_reg="DL30JD1420"
        ),
        "Mock"
    ))
    
    # We must mock store.search_evidence to return NO allowed evidence, but SOME rejected evidence
    from src.models import EvidenceCandidate, AuditEvent
    monkeypatch.setattr("src.context_store.ContextStore.search_evidence", lambda self, ticket, limit=10: (
        [], # allowed
        [AuditEvent(
            event_id="AUD-REJ", ticket_id="TKT-FALLBACK-05", step_number=1, step_name="CROSS_CONTAMINATION_FILTER",
            decision="Rejected CLIENT_SPECIFIC", input_data_summary={}, rule_applied="", source_citations=[], timestamp=""
        )] # rejected
    ))

    raw_ticket = {
        "ticket_id": "TKT-FALLBACK-05",
        "client_name": "Apex Chemicals",
        "fault": "kal raat wali gaadi broke down",
        "created_at": "2026-08-30T10:00:00Z"
    }

    test_file = tmp_path / "temp.json"
    with open(test_file, "w") as f2:
        import json
        json.dump([raw_ticket], f2)
    work_orders, comms, quarantine, audit = test_pipeline.process_ticket_queue(test_file)
    
    assert len(quarantine) > 0
    q_record = quarantine[-1]
    assert "TKT-FALLBACK-05" in q_record.ticket_id
    assert "CONTEXT_UNCERTAIN/AMBIGUOUS_ENTITY" in q_record.reason_code
    assert "no corroborating evidence found" in q_record.reason_code
