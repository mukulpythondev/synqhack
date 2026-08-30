import sys
import json
from pathlib import Path
from src.config import (
    WORK_ORDERS_PATH,
    COMMS_PENDING_PATH,
    COMMS_SENT_PATH,
    QUARANTINE_PATH,
    AUDIT_PATH
)

def inspect(ticket_id: str):
    tid = ticket_id.strip()
    
    # 1. Gather Quarantine
    q_item = None
    if QUARANTINE_PATH.exists():
        with open(QUARANTINE_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    if item.get("ticket_id") == tid:
                        q_item = item
                        break

    # 2. Gather Work Order
    wo_item = None
    if WORK_ORDERS_PATH.exists():
        with open(WORK_ORDERS_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    if item.get("ticket_id") == tid:
                        wo_item = item
                        break
                        
    # 3. Gather Comms
    comm_item = None
    if COMMS_SENT_PATH.exists():
        with open(COMMS_SENT_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    if item.get("ticket_id") == tid:
                        comm_item = item
                        break
    if not comm_item and COMMS_PENDING_PATH.exists():
        with open(COMMS_PENDING_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    if item.get("ticket_id") == tid:
                        comm_item = item
                        comm_item["status_label"] = "PENDING APPROVAL"
                        break

    # 4. Gather Audit
    audit_records = []
    if AUDIT_PATH.exists():
        with open(AUDIT_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    if item.get("ticket_id") == tid:
                        audit_records.append(item)
    
    audit_records.sort(key=lambda x: x.get("step_number", 0))

    if not q_item and not wo_item and not audit_records:
        print(f"Ticket {tid} not found in any outboxes or audit logs.")
        return

    # Infer Input
    raw_input = {}
    if q_item:
        raw_input = q_item.get("sanitized_record", {})
    elif audit_records:
        # Step 1 should have input data summary
        raw_input = audit_records[0].get("input_data_summary", {})

    status = "RESOLVED" if wo_item else ("QUARANTINED" if q_item else "PROCESSING")

    print("====================================================")
    print("MERIDIAN FREIGHT — TICKET TRACE")
    print("====================================================")
    print(f"\nTICKET\nID: {tid}\nSTATUS: {status}")
    
    print("\nINPUT")
    print(f"Vehicle: {raw_input.get('vehicle', raw_input.get('vehicle_reg', 'N/A'))}")
    print(f"Driver: {raw_input.get('driver_id', 'N/A')}")
    print(f"Client: {raw_input.get('client', raw_input.get('client_name', 'N/A'))}")
    print(f"Origin: {raw_input.get('origin_hub', 'N/A')}")
    print(f"Destination: {raw_input.get('destination', 'N/A')}")
    print(f"Issue: {raw_input.get('issue', 'N/A')}")
    print(f"Created: {raw_input.get('created_at', 'N/A')}")

    print("\nCONTEXT")
    # Derived from audit steps
    enrichment_step = next((a for a in audit_records if a.get("step_name") == "CONTEXT_ENRICHMENT"), None)
    if enrichment_step:
        print(f"Sources: {', '.join(enrichment_step.get('source_citations', []))}")
    else:
        print("Sources: N/A")

    print("\nEVIDENCE RETRIEVAL")
    print("Structured: ACTIVE")
    print("FTS5: ACTIVE")
    print("Semantic: SKIPPED (Local constraint)")
    
    # Check for Gemini Fallback
    gemini_step = next((a for a in audit_records if a.get("step_name") == "GEMINI_PERCEPTION_FALLBACK"), None)
    if gemini_step:
        print("\nGEMINI PERCEPTION FALLBACK")
        print("Status: INVOKED")
        print(f"Decision: {gemini_step.get('decision')}")
        extracted = gemini_step.get("input_data_summary", {}).get("extracted", {})
        print(f"Extracted Facts: {extracted}")
        print(f"Extraction Method: {gemini_step.get('input_data_summary', {}).get('method')}")
        print(f"Accepted Evidence: {', '.join(gemini_step.get('source_citations', []))}")
        print(f"Corroboration Rule: {gemini_step.get('rule_applied')}")
    else:
        print("\nGEMINI PERCEPTION FALLBACK")
        print("Status: SKIPPED (Deterministic perception succeeded)")

    print("\nENTITY CORROBORATION")
    if enrichment_step:
        print(f"Decision: {enrichment_step.get('decision')}")
    else:
        print("Decision: N/A")
        
    print("\nREJECTED EVIDENCE")
    rejected_count = 0
    for a in audit_records:
        if a.get("step_name") == "CROSS_CONTAMINATION_FILTER":
            print(f"- {a.get('source_citations', [''])[0]} : {a.get('decision')}")
            rejected_count += 1
    if rejected_count == 0:
        print("None")

    print("\nRULE EVALUATION")
    for a in audit_records:
        if "RULE" in a.get("rule_applied", "") or a.get("step_name") == "ALLOCATE_REPLACEMENT":
            print(f"[{a.get('step_name')}] {a.get('rule_applied')} -> {a.get('decision')}")

    print("\nALLOCATION")
    if wo_item:
        print(f"Selected vehicle: {wo_item.get('vehicle_reg')}")
        alloc_step = next((a for a in audit_records if a.get("step_name") == "ALLOCATE_REPLACEMENT"), None)
        if alloc_step:
            print(f"Eligibility Rule: {alloc_step.get('rule_applied')}")
            print(f"Citations: {', '.join(alloc_step.get('source_citations', []))}")
    else:
        print("Selected vehicle: N/A")

    print("\nWORK ORDER")
    if wo_item:
        print(f"ID: {wo_item.get('work_order_id')}")
        print("STATUS: CREATED")
    else:
        print("STATUS: N/A")

    print("\nCOMMUNICATION")
    if comm_item:
        print(f"STATUS: {comm_item.get('status_label', 'APPROVED & SENT')}")
        print(f"Recipient: {comm_item.get('recipient')}")
        print(f"SLA Type: {comm_item.get('sla_type', 'N/A')}")
    else:
        print("STATUS: N/A")

    print("\nQUARANTINE")
    if q_item:
        category, _, reason = q_item.get("reason_code", "").partition(" (")
        print(f"CATEGORY: {category}")
        print(f"REASON: {reason.strip(')')}")
    else:
        print("CATEGORY: N/A")

    print("\nAUDIT")
    print(f"Steps: {len(audit_records)}")
    for a in audit_records:
        print(f"  - Step {a.get('step_number')}: {a.get('step_name')}")
        
    print("====================================================")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("\nUsage: python inspect_ticket.py <TICKET_ID>")
        print("Example: python inspect_ticket.py TKT-0027\n")
        sys.exit(1)

    inspect(sys.argv[1])
