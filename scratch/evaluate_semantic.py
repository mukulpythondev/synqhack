import sys
from pathlib import Path
from datetime import datetime
from src.context_store import ContextStore
from src.models import CanonicalTicket

def create_mock_ticket(ticket_id, issue, client_name="UNKNOWN", vehicle="", driver=""):
    return CanonicalTicket(
        ticket_id=ticket_id,
        sanitized_input_snapshot={},
        created_at="2026-08-30T10:00:00",
        event_timestamp=datetime(2026, 8, 30, 10, 0, 0),
        vehicle_reg_canonical=vehicle,
        driver_id=driver,
        origin_hub="Delhi",
        destination="Kanpur",
        km_from_origin_hub=10.0,
        issue=issue,
        severity="MEDIUM",
        client_name=client_name,
        is_valid=True
    )

def run_evaluation():
    from src.config import STATE_DB_PATH
    store = ContextStore(STATE_DB_PATH)
    
    cases = [
        {
            "query_desc": "Contextual Reference ('Kal raat wali gaadi')",
            "ticket": create_mock_ticket("TKT-0025", "engine check kal raat wali gaadi", client_name="UNKNOWN"),
            "expected": "thread_25_internal_jugaad.txt",
        },
        {
            "query_desc": "Implicit vehicle reference (paraphrase)",
            "ticket": create_mock_ticket("TKT-0012", "delayed due to congestion near gate", client_name="Vertex Retail"),
            "expected": "thread_09_vertex_gate.txt",
        },
        {
            "query_desc": "Semantic paraphrase of SLA",
            "ticket": create_mock_ticket("TKT-0030", "how many hours can delivery take", client_name="Shakti Cement"),
            "expected": "thread_01_shakti_sla.txt",
        },
        {
            "query_desc": "Explicit vehicle/client",
            "ticket": create_mock_ticket("TKT-0005", "breakdown enroute", client_name="Apex Chemicals", vehicle="UP14BT8899"),
            "expected": "thread_13_apex_rotation.txt",
        }
    ]
    
    print(f"{'Case':<45} | {'FTS5 Found':<12} | {'SEMANTIC Found':<15} | {'SEMANTIC Rank'}")
    print("-" * 90)
    
    for c in cases:
        t = c["ticket"]
        # FTS5
        fts_res = store.search_evidence(t, limit=10)
        fts_found = any(c["expected"] in r.source_file for r in fts_res)
        
        # Semantic
        sem_res = store.semantic_search_evidence(t, limit=10)
        sem_found = False
        sem_rank = "-"
        for i, r in enumerate(sem_res):
            if c["expected"] in r.source_file:
                sem_found = True
                sem_rank = str(i+1)
                break
                
        print(f"{c['query_desc']:<45} | {'Yes' if fts_found else 'No':<12} | {'Yes' if sem_found else 'No':<15} | {sem_rank}")

if __name__ == "__main__":
    run_evaluation()
