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
