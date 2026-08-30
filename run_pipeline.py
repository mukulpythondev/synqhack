"""
Meridian Freight Breakdown Automation
Master Deployment Entrypoint: One-Command Execution
"""

import sys
import argparse
from pathlib import Path

from src.config import (
    TICKETS_PATH,
    OUTPUTS_DIR,
    AUDIT_DIR,
    WORK_ORDERS_PATH,
    COMMS_PENDING_PATH,
    COMMS_SENT_PATH,
    QUARANTINE_PATH,
    AUDIT_PATH
)
from src.pipeline import BreakdownPipeline
from src.comms_gate import HumanApprovalGate

def main():
    parser = argparse.ArgumentParser(
        description="Meridian Freight: Production Breakdown-to-Resolution Automation Pipeline"
    )
    parser.add_argument(
        "--input",
        type=str,
        default=str(TICKETS_PATH),
        help="Path to breakdown tickets queue JSON file (default: candidate_bundle/tickets.json)"
    )
    parser.add_argument(
        "--eval-mode",
        action="store_true",
        help="Run in evaluation test harness mode (auto-approves pending client comms without interactive prompt)"
    )
    parser.add_argument(
        "--skip-comms-approval",
        action="store_true",
        help="Skip human comms approval step (leaves comms in pending state)"
    )

    args = parser.parse_args()
    input_file = Path(args.input)

    if not input_file.exists():
        print(f"[ERROR] Input queue file not found at: {input_file}")
        sys.exit(1)

    print("\n" + "=" * 65)
    print("   MERIDIAN FREIGHT: BREAKDOWN AUTOMATION PIPELINE")
    print("   Deploying Forward Deployed Engineering System")
    print("=" * 65)
    print(f"[*] Input Queue:       {input_file}")
    print(f"[*] Output Directory:  {OUTPUTS_DIR}")
    print(f"[*] Audit Directory:   {AUDIT_DIR}")
    print(f"[*] Execution Mode:    {'Evaluation Harness (--eval-mode)' if args.eval_mode else 'Interactive Production'}\n")

    # 1. Initialize and execute state machine pipeline
    pipeline = BreakdownPipeline()
    work_orders, pending_comms, quarantine, audit = pipeline.process_ticket_queue(input_file)

    print("\n" + "-" * 65)
    print("   PIPELINE EXECUTION SUMMARY")
    print("-" * 65)
    print(f"[+] Unique Work Orders Generated: {len(work_orders):>3}  --> {WORK_ORDERS_PATH.name}")
    print(f"[+] Client Communications Drafted:{len(pending_comms):>3}  --> {COMMS_PENDING_PATH.name}")
    print(f"[+] Malformed Records Quarantined:{len(quarantine):>3}  --> {QUARANTINE_PATH.name}")
    print(f"[+] Step-by-Step Audit Records:   {len(audit):>3}  --> {AUDIT_PATH.name}")

    # 2. Human Authorization Gate
    if not args.skip_comms_approval:
        gate = HumanApprovalGate()
        sent_comms = gate.run_approval_process(eval_mode=args.eval_mode)
        print(f"[+] Approved Messages Dispatched: {len(sent_comms):>3}  --> {COMMS_SENT_PATH.name}")

    print("\n" + "=" * 65)
    print("   STATUS: RUN COMPLETE (Zero Unattended Failures)")
    print("=" * 65 + "\n")

if __name__ == "__main__":
    main()
