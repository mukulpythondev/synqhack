"""
Meridian Freight Breakdown Automation
Breakdown-to-Resolution State Machine & Orchestrator
"""

import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple

from src.config import (
    WORK_ORDERS_PATH,
    COMMS_PENDING_PATH,
    COMMS_SENT_PATH,
    QUARANTINE_PATH,
    AUDIT_PATH,
    OUTPUTS_DIR,
    AUDIT_DIR,
    CLIENT_METADATA,
    STATE_DB_PATH
)
from src.models import (
    CanonicalTicket,
    CanonicalVehicle,
    WorkOrderOutput,
    CommsPendingOutput,
    CommsSentOutput,
    QuarantineOutput,
    AuditEvent
)
from src.context_store import ContextStore
from src.rule_engine import RuleEngine
from src.allocator import ReplacementAllocator
from src.adapter import DynamicTicketAdapter
from src.pii_scrubber import PIIScrubber

class BreakdownPipeline:
    """
    State machine and processing pipeline.
    Enforces deterministic idempotency, exactly-once actions, and zero-PII security gates.
    """

    def __init__(self, state_db_path: Optional[Path] = None):
        self.store = ContextStore(state_db_path or STATE_DB_PATH)
        self.rule_engine = RuleEngine(self.store)
        self.allocator = ReplacementAllocator(self.store, self.rule_engine)
        
        # Ensure output directories exist
        OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
        AUDIT_DIR.mkdir(parents=True, exist_ok=True)

    def process_ticket_queue(
        self,
        tickets_file_path: Path
    ) -> Tuple[List[WorkOrderOutput], List[CommsPendingOutput], List[QuarantineOutput], List[AuditEvent]]:
        """
        Consumes a queue of tickets and processes them end-to-end.
        """
        with open(tickets_file_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        if not isinstance(raw_data, list):
            raise ValueError(f"Expected a JSON list of ticket objects in {tickets_file_path}")

        work_orders: List[WorkOrderOutput] = []
        pending_comms: List[CommsPendingOutput] = []
        quarantine_records: List[QuarantineOutput] = []
        audit_records: List[AuditEvent] = []

        seen_ticket_ids: Set[str] = set()
        assigned_vehicles: Set[str] = set()

        for idx, raw_record in enumerate(raw_data):
            # Step 1: Ingestion, PII Scrub, Dynamic Adapter & Validation
            ticket = DynamicTicketAdapter.adapt_record(raw_record)
            
            # Quarantine Check
            if not ticket.is_valid:
                quarantine_entry = QuarantineOutput(
                    ticket_id=ticket.ticket_id,
                    sanitized_record=ticket.sanitized_input_snapshot,
                    reason_code=ticket.quarantine_reason or "CORRUPTED_PAYLOAD",
                    quarantined_at=ticket.created_at
                )
                quarantine_records.append(quarantine_entry)

                audit_records.append(AuditEvent(
                    event_id=f"AUD-{ticket.ticket_id}-01",
                    ticket_id=ticket.ticket_id,
                    step_number=1,
                    step_name="VALIDATE_AND_QUARANTINE",
                    decision=f"Quarantined: {ticket.quarantine_reason}",
                    input_data_summary={"ticket_id": ticket.ticket_id},
                    rule_applied="RULE_SAFETY_QUARANTINE",
                    source_citations=["candidate_bundle/tickets.json"],
                    timestamp=ticket.created_at
                ))
                continue

            # Deduplication Check (Exactly-Once Invariant)
            if ticket.ticket_id in seen_ticket_ids:
                audit_records.append(AuditEvent(
                    event_id=f"AUD-{ticket.ticket_id}-DUP-{idx}",
                    ticket_id=ticket.ticket_id,
                    step_number=1,
                    step_name="DEDUPLICATION_GATE",
                    decision="Duplicate ticket instance ignored; no duplicate work order or message generated.",
                    input_data_summary={"ticket_id": ticket.ticket_id},
                    rule_applied="IDEMPOTENCY_EXACTLY_ONCE",
                    source_citations=["CANDIDATE_README.md:Rule_1"],
                    timestamp=ticket.created_at
                ))
                continue

            seen_ticket_ids.add(ticket.ticket_id)

            # Step 1.5: Client Contract Verification Gate
            if ticket.client_name not in CLIENT_METADATA:
                quarantine_entry = QuarantineOutput(
                    ticket_id=ticket.ticket_id,
                    sanitized_record=ticket.sanitized_input_snapshot,
                    reason_code=f"INSUFFICIENT_DATA (Unregistered client with unknown SLA contract: '{ticket.client_name}')",
                    quarantined_at=ticket.created_at
                )
                quarantine_records.append(quarantine_entry)

                audit_records.append(AuditEvent(
                    event_id=f"AUD-{ticket.ticket_id}-01-CLIENT",
                    ticket_id=ticket.ticket_id,
                    step_number=1,
                    step_name="VALIDATE_CLIENT_CONTRACT",
                    decision=f"Quarantined: Unregistered client '{ticket.client_name}' lacks verified SLA specification.",
                    input_data_summary={"client": ticket.client_name},
                    rule_applied="RULE_CLIENT_VERIFICATION",
                    source_citations=["candidate_bundle/CANDIDATE_README.md:Client_Contracts"],
                    timestamp=ticket.created_at
                ))
                continue

            # Step 2: Context Enrichment & Driver Safety Check
            is_driver_safe, driver_action, driver_citations = self.rule_engine.evaluate_driver_safety(ticket)
            
            audit_records.append(AuditEvent(
                event_id=f"AUD-{ticket.ticket_id}-02",
                ticket_id=ticket.ticket_id,
                step_number=2,
                step_name="CONTEXT_ENRICHMENT",
                decision=f"Enriched with driver {ticket.driver_id}, client {ticket.client_name}, vehicle {ticket.vehicle_reg_canonical}. Driver status: {driver_action}",
                input_data_summary={"client": ticket.client_name, "driver_id": ticket.driver_id, "origin": ticket.origin_hub},
                rule_applied="RULE_07_DRIVER_NIGHT_SOLO_RESTRICTION" if not is_driver_safe else "STANDARD_ENRICHMENT",
                source_citations=sorted(driver_citations) if not is_driver_safe else ["drivers_roster.csv", "fleet_master.csv"],
                timestamp=ticket.created_at
            ))

            # Step 3: Replacement Vehicle Allocation (Allowed Hubs + Eligibility + 3-Tier Ranking)
            winner_vehicle, alloc_citations, why_not_map = self.allocator.allocate_replacement_vehicle(
                ticket, assigned_vehicles
            )

            if not winner_vehicle:
                # No eligible vehicle found -> Quarantine with Insufficient Fleet alert
                quarantine_entry = QuarantineOutput(
                    ticket_id=ticket.ticket_id,
                    sanitized_record=ticket.sanitized_input_snapshot,
                    reason_code="INSUFFICIENT_DATA (No eligible replacement vehicle available)",
                    quarantined_at=ticket.created_at
                )
                quarantine_records.append(quarantine_entry)
                continue

            assigned_vehicles.add(winner_vehicle.registration_canonical)

            audit_records.append(AuditEvent(
                event_id=f"AUD-{ticket.ticket_id}-03",
                ticket_id=ticket.ticket_id,
                step_number=3,
                step_name="ALLOCATE_REPLACEMENT",
                decision=f"Allocated replacement vehicle {winner_vehicle.registration_canonical} ({winner_vehicle.model}, {winner_vehicle.bs_stage}) from {winner_vehicle.home_hub} hub.",
                input_data_summary={"client": ticket.client_name, "distance_km": ticket.km_from_origin_hub, "origin_hub": ticket.origin_hub},
                rule_applied="RULE_03_ORIGIN_PROXIMITY_50KM",
                source_citations=sorted(alloc_citations),
                timestamp=ticket.created_at
            ))

            # Step 4: Generate Deterministic Work Order
            work_order = WorkOrderOutput(
                work_order_id=f"WO-{ticket.ticket_id}",
                ticket_id=ticket.ticket_id,
                vehicle_reg=winner_vehicle.registration_canonical,
                created_at=ticket.created_at,
                citations=sorted(alloc_citations)
            )
            work_orders.append(work_order)

            audit_records.append(AuditEvent(
                event_id=f"AUD-{ticket.ticket_id}-04",
                ticket_id=ticket.ticket_id,
                step_number=4,
                step_name="CREATE_WORK_ORDER",
                decision=f"Created work order {work_order.work_order_id} assigning {winner_vehicle.registration_canonical}.",
                input_data_summary={"vehicle_reg": winner_vehicle.registration_canonical, "work_order_id": work_order.work_order_id},
                rule_applied="WORK_ORDER_SPECIFICATION",
                source_citations=sorted(alloc_citations),
                timestamp=ticket.created_at
            ))

            # Step 5: Evaluate Client SLA & Draft Client Communication
            sla_desc, effective_eta, sla_citations = self.rule_engine.evaluate_client_sla_and_eta(ticket, base_osrm_hours=24.0)
            client_meta = CLIENT_METADATA.get(ticket.client_name, CLIENT_METADATA["Internal"])
            recipient = client_meta["email_recipient"]

            proposed_body = (
                f"Operational Update: Breakdown reported on {ticket.origin_hub} to {ticket.destination} route "
                f"for vehicle {ticket.vehicle_reg_canonical}. Replacement vehicle {winner_vehicle.registration_canonical} "
                f"dispatched from {winner_vehicle.home_hub} hub. Consignment status: {sla_desc}."
            )

            all_comms_citations = sorted(list(set(alloc_citations + sla_citations)))
            pending_comm = CommsPendingOutput(
                draft_id=f"DRAFT-{ticket.ticket_id}",
                ticket_id=ticket.ticket_id,
                recipient=recipient,
                proposed_body=proposed_body,
                sla_type=sla_desc,
                replacement_vehicle=winner_vehicle.registration_canonical,
                citations=all_comms_citations
            )
            pending_comms.append(pending_comm)

            audit_records.append(AuditEvent(
                event_id=f"AUD-{ticket.ticket_id}-05",
                ticket_id=ticket.ticket_id,
                step_number=5,
                step_name="DRAFT_CLIENT_COMMUNICATION",
                decision=f"Drafted client communication to {recipient} with SLA: {sla_desc}",
                input_data_summary={"client": ticket.client_name, "recipient": recipient, "sla": sla_desc},
                rule_applied="CLIENT_SLA_GOVERNANCE",
                source_citations=all_comms_citations,
                timestamp=ticket.created_at
            ))

            # Record in SQLite persistent state table
            self.store.record_processed_ticket(
                ticket_id=ticket.ticket_id,
                status="PROCESSED",
                work_order_id=work_order.work_order_id,
                replacement_reg=winner_vehicle.registration_canonical,
                is_approved=0,
                processed_at=ticket.created_at
            )

        # Write output files deterministically
        self._write_outputs(work_orders, pending_comms, quarantine_records, audit_records)
        return work_orders, pending_comms, quarantine_records, audit_records

    def _write_outputs(
        self,
        work_orders: List[WorkOrderOutput],
        pending_comms: List[CommsPendingOutput],
        quarantine: List[QuarantineOutput],
        audit: List[AuditEvent]
    ):
        """
        Serializes output JSONL files with sorted keys and deterministic ticket_id ordering.
        Passes all writes through pre-commit PII validation gate.
        """
        # 1. work_orders.jsonl
        sorted_wo = sorted(work_orders, key=lambda x: x.ticket_id)
        with open(WORK_ORDERS_PATH, "w", encoding="utf-8") as f:
            for wo in sorted_wo:
                payload = wo.to_dict()
                PIIScrubber.validate_outbox_payload(payload)
                f.write(json.dumps(payload, sort_keys=True) + "\n")

        # 2. comms_pending.jsonl
        sorted_pending = sorted(pending_comms, key=lambda x: x.ticket_id)
        with open(COMMS_PENDING_PATH, "w", encoding="utf-8") as f:
            for comm in sorted_pending:
                payload = comm.to_dict()
                PIIScrubber.validate_outbox_payload(payload)
                f.write(json.dumps(payload, sort_keys=True) + "\n")

        # 3. quarantine.jsonl
        sorted_quarantine = sorted(quarantine, key=lambda x: x.ticket_id)
        with open(QUARANTINE_PATH, "w", encoding="utf-8") as f:
            for q in sorted_quarantine:
                payload = q.to_dict()
                PIIScrubber.validate_outbox_payload(payload)
                f.write(json.dumps(payload, sort_keys=True) + "\n")

        # 4. audit.jsonl
        sorted_audit = sorted(audit, key=lambda x: (x.ticket_id, x.step_number, x.event_id))
        with open(AUDIT_PATH, "w", encoding="utf-8") as f:
            for a in sorted_audit:
                payload = a.to_dict()
                PIIScrubber.validate_outbox_payload(payload)
                f.write(json.dumps(payload, sort_keys=True) + "\n")
