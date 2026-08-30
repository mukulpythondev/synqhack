from src.evidence_filter import EvidenceFilter

def test_cross_contamination_filters():
    # 1. Shakti ticket + Apex-specific email -> Apex evidence rejected
    candidates = [
        {"id": "doc1", "text": "Apex Chemicals reported a breakdown.", "source": "email1"}
    ]
    allowed, audit = EvidenceFilter.filter_candidates("TKT-001", "Shakti Cement", candidates)
    assert len(allowed) == 0
    assert len(audit) == 1
    assert "Rejected CLIENT_SPECIFIC evidence" in audit[0].decision
    assert audit[0].input_data_summary["candidate_id"] == "doc1"
    
    # 2. Shakti ticket + global dispatcher policy -> policy allowed
    candidates = [
        {"id": "doc2", "text": "Global dispatcher policy: 50km radius.", "source": "policy1"}
    ]
    allowed, audit = EvidenceFilter.filter_candidates("TKT-002", "Shakti Cement", candidates)
    assert len(allowed) == 1
    assert len(audit) == 0
    
    # 3. unknown-client ticket -> no artificial client filter
    candidates = [
        {"id": "doc3", "text": "Apex Chemicals reported an issue.", "source": "email2"}
    ]
    allowed, audit = EvidenceFilter.filter_candidates("TKT-003", "UNKNOWN", candidates)
    assert len(allowed) == 1
    assert len(audit) == 0
    
    # 4. same-client evidence -> allowed
    candidates = [
        {"id": "doc4", "text": "Shakti Cement incident on hill route.", "source": "email3"}
    ]
    allowed, audit = EvidenceFilter.filter_candidates("TKT-004", "Shakti Cement", candidates)
    assert len(allowed) == 1
    assert len(audit) == 0
