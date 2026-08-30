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
            "ticket": create_mock_ticket("TKT-0025", "engine check needed", client_name="Internal"),
            "expected": "thread_25_internal_jugaad.txt",
            "notes": "Testing if FTS5 can bridge 'kal raat wali gaadi' without exact vehicle ID."
        },
        {
            "query_desc": "Vertex Retail SLA exception",
            "ticket": create_mock_ticket("TKT-0012", "delay in transit", client_name="Vertex Retail"),
            "expected": "thread_09_vertex_gate.txt",
            "notes": "Testing retrieval of SLA rules based on client name."
        },
        {
            "query_desc": "Apex Chemicals Incident Rotation",
            "ticket": create_mock_ticket("TKT-0005", "breakdown enroute", client_name="Apex Chemicals", vehicle="UP14BT8899"),
            "expected": "thread_13_apex_rotation.txt",
            "notes": "Testing exact vehicle/client match."
        },
        {
            "query_desc": "Maintenance Jugaad Check",
            "ticket": create_mock_ticket("TKT-0040", "brake overheating", vehicle="CH67HY8613"),
            "expected": "maintenance_log.xlsx",
            "notes": "Testing if maintenance notes are retrieved for vehicle."
        },
        {
            "query_desc": "Cross Client Rejection (Shakti)",
            "ticket": create_mock_ticket("TKT-0030", "plant delivery", client_name="Shakti Cement"),
            "expected": "thread_01_shakti_sla.txt",
            "notes": "Testing if Apex/Vertex emails are successfully rejected."
        }
    ]
    
    out_path = Path("CANDIDATE_BUNDLE_FTS5_EVALUATION.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# FTS5 Real Data Evaluation\n\n")
        f.write("| Case | Query/Ticket Context | Expected Evidence | Found? | Rank | Candidates | Cross-Client Rejected? | Notes |\n")
        f.write("|------|----------------------|-------------------|--------|------|------------|------------------------|-------|\n")
        
        for c in cases:
            t = c["ticket"]
            results = store.search_evidence(t, limit=10)
            
            found = "No"
            rank = "-"
            sources = []
            
            for i, r in enumerate(results):
                sources.append(r.source_file)
                if c["expected"] in r.source_file and found == "No":
                    found = "Yes"
                    rank = str(i+1)
            
            # Check for cross-client
            cross_rejected = "N/A"
            if t.client_name == "Shakti Cement":
                has_apex = any("apex" in s.lower() for s in sources)
                cross_rejected = "Yes" if not has_apex else "Failed"
            
            f.write(f"| {c['query_desc']} | Client: {t.client_name}<br>Vehicle: {t.vehicle_reg_canonical}<br>Issue: {t.issue} | {c['expected']} | {found} | {rank} | {len(results)} | {cross_rejected} | {c['notes']} |\n")
            
    print("Evaluation complete. Report generated at CANDIDATE_BUNDLE_FTS5_EVALUATION.md")

if __name__ == "__main__":
    run_evaluation()
