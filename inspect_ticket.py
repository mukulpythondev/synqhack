"""
Meridian Freight Breakdown Automation
Evaluator Observability: 30-Second Ticket Decision Inspector
"""

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
    print("\n" + "=" * 70)
    print(f"   MERIDIAN FREIGHT: TICKET DECISION TRACE [{tid}]")
    print("=" * 70)

    # 1. Check Quarantine
    is_quarantined = False
    if QUARANTINE_PATH.exists():
        with open(QUARANTINE_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    if item.get("ticket_id") == tid:
                        is_quarantined = True
                        print(f"\n[!] STATUS: QUARANTINED")
                        print(f"    Reason Code:     {item.get('reason_code')}")
                        print(f"    Quarantined At:  {item.get('quarantined_at')}")
                        print(f"    Sanitized Data:  {item.get('sanitized_record')}")
                        break

    # 2. Check Work Order
    wo_item = None
    if WORK_ORDERS_PATH.exists():
        with open(WORK_ORDERS_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    if item.get("ticket_id") == tid:
                        wo_item = item
                        break

    if wo_item:
        print(f"\n[+] STATUS: RESOLVED & WORK ORDER CREATED")
        print(f"    Work Order ID:       {wo_item.get('work_order_id')}")
        print(f"    Assigned Vehicle:    {wo_item.get('vehicle_reg')}")
        print(f"    Created Timestamp:   {wo_item.get('created_at')}")
        print(f"    Citations:")
        for c in wo_item.get("citations", []):
            print(f"      - {c}")

    # 3. Check Communications
    if COMMS_SENT_PATH.exists():
        with open(COMMS_SENT_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    if item.get("ticket_id") == tid:
                        print(f"\n[+] CLIENT COMMUNICATION: APPROVED & DISPATCHED")
                        print(f"    Message ID:   {item.get('message_id')}")
                        print(f"    Recipient:    {item.get('recipient')}")
                        print(f"    Approved By:  {item.get('approved_by')}")
                        print(f"    Sent At:      {item.get('sent_at')}")
                        print(f"    Body:\n      \"{item.get('body')}\"")
                        break

    # 4. Audit Trail
    print(f"\n[-] STEP-BY-STEP AUDIT TRAIL:")
    found_audit = False
    if AUDIT_PATH.exists():
        with open(AUDIT_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    if item.get("ticket_id") == tid:
                        found_audit = True
                        step_num = item.get("step_number")
                        step_name = item.get("step_name")
                        decision = item.get("decision")
                        rule = item.get("rule_applied")
                        print(f"    Step {step_num} [{step_name}]:")
                        print(f"      Decision: {decision}")
                        print(f"      Rule:     {rule}")
    if not found_audit and not is_quarantined:
        print(f"    No audit records found for {tid}.")

    print("\n" + "=" * 70 + "\n")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("\nUsage: python inspect_ticket.py <TICKET_ID>")
        print("Example: python inspect_ticket.py TKT-0027\n")
        sys.exit(1)

    inspect(sys.argv[1])
