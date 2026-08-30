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
from src.logger import get_structured_logger

logger = get_structured_logger("MeridianPipeline")

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
            
            # --- NEW GEMINI FALLBACK ARCHITECTURE ---
            if not ticket.is_valid and ticket.quarantine_reason and ticket.quarantine_reason.startswith("DATA_INVALID/UNRESOLVED_VEHICLE") and ticket.issue:
                # 1. Retrieve bounded evidence
                allowed_evidence, rejected_evidence = self.store.search_evidence(ticket)
                if rejected_evidence:
                    audit_records.extend(rejected_evidence)
                    logger.info(f"Rejected {len(rejected_evidence)} evidence snippets for cross-contamination during fallback", extra={"structured_data": {"ticket_id": ticket.ticket_id}})
                
                context_texts = [e.sanitized_snippet for e in allowed_evidence]
                context_str = "\n".join(context_texts)
                
                # 2. Gemini perception (using bounded evidence + issue text)
                from src.llm_adapter import PerceptionRouter
                router = PerceptionRouter()
                facts, extracted_by = router.extract_facts(ticket.issue, context_source=context_str)
                
                # 3. Deterministic entity validation
                gemini_vehicle = facts.vehicle_reg
                if gemini_vehicle and facts.confidence > 0.7:
                    from src.normalizer import normalize_vehicle_reg
                    canon_reg, is_valid_plate = normalize_vehicle_reg(gemini_vehicle)
                    if is_valid_plate:
                        # 4. Corroboration
                        if self.store.get_vehicle(canon_reg) is not None:
                            if allowed_evidence: # Must have corroborating evidence
                                from dataclasses import replace
                                ticket = replace(
                                    ticket,
                                    vehicle_reg_canonical=canon_reg,
                                    is_valid=True,
                                    quarantine_reason=None,
                                    client_name=ticket.client_name or facts.client,
                                    driver_id=ticket.driver_id or facts.driver_id
                                )
                                logger.info(f"Gemini safely extracted corroborated vehicle {canon_reg}", extra={"structured_data": {"ticket_id": ticket.ticket_id}})
                                audit_records.append(AuditEvent(
                                    event_id=f"AUD-{ticket.ticket_id}-GEMINI",
                                    ticket_id=ticket.ticket_id,
                                    step_number=1,
                                    step_name="GEMINI_PERCEPTION_FALLBACK",
                                    decision=f"VERIFIED: Extracted {canon_reg} from context",
                                    input_data_summary={"extracted": facts.model_dump(), "method": extracted_by},
                                    rule_applied="CORROBORATED_ENTITY",
                                    source_citations=[e.source_file for e in allowed_evidence],
                                    timestamp=ticket.created_at
                                ))
                            else:
                                from dataclasses import replace
                                ticket = replace(ticket, quarantine_reason="CONTEXT_UNCERTAIN/AMBIGUOUS_ENTITY (Gemini proposed vehicle but no corroborating evidence found)")
                                audit_records.append(AuditEvent(
                                    event_id=f"AUD-{ticket.ticket_id}-GEMINI",
                                    ticket_id=ticket.ticket_id,
                                    step_number=1,
                                    step_name="GEMINI_PERCEPTION_FALLBACK",
                                    decision="CONTEXT_UNCERTAIN: No corroborating evidence",
                                    input_data_summary={"extracted": facts.model_dump(), "method": extracted_by},
                                    rule_applied="REJECT_UNCORROBORATED",
                                    source_citations=[],
                                    timestamp=ticket.created_at
                                ))
                        else:
                            from dataclasses import replace
                            ticket = replace(ticket, quarantine_reason=f"CONTEXT_UNCERTAIN/AMBIGUOUS_ENTITY (Gemini proposed non-existent vehicle {canon_reg})")
                            audit_records.append(AuditEvent(
                                event_id=f"AUD-{ticket.ticket_id}-GEMINI",
                                ticket_id=ticket.ticket_id,
                                step_number=1,
                                step_name="GEMINI_PERCEPTION_FALLBACK",
                                decision=f"CONTEXT_UNCERTAIN: Non-existent vehicle {canon_reg}",
                                input_data_summary={"extracted": facts.model_dump(), "method": extracted_by},
                                rule_applied="REJECT_NONEXISTENT",
                                source_citations=[],
                                timestamp=ticket.created_at
                            ))
                    else:
                        from dataclasses import replace
                        ticket = replace(ticket, quarantine_reason=f"CONTEXT_UNCERTAIN/AMBIGUOUS_ENTITY (Gemini proposed invalid registration format)")
                        audit_records.append(AuditEvent(
                                event_id=f"AUD-{ticket.ticket_id}-GEMINI",
                                ticket_id=ticket.ticket_id,
                                step_number=1,
                                step_name="GEMINI_PERCEPTION_FALLBACK",
                                decision="CONTEXT_UNCERTAIN: Invalid registration format",
                                input_data_summary={"extracted": facts.model_dump(), "method": extracted_by},
                                rule_applied="REJECT_INVALID_FORMAT",
                                source_citations=[],
                                timestamp=ticket.created_at
                            ))
                else:
                    if not ticket.quarantine_reason.startswith("CONTEXT_UNCERTAIN/AMBIGUOUS_ENTITY"):
                        from dataclasses import replace
                        ticket = replace(ticket, quarantine_reason=f"CONTEXT_UNCERTAIN/AMBIGUOUS_ENTITY (Gemini could not confidently extract vehicle)")
                    
                    audit_records.append(AuditEvent(
                        event_id=f"AUD-{ticket.ticket_id}-GEMINI",
                        ticket_id=ticket.ticket_id,
                        step_number=1,
                        step_name="GEMINI_PERCEPTION_FALLBACK",
                        decision="CONTEXT_UNCERTAIN: Low confidence or unavailable",
                        input_data_summary={"extracted": facts.model_dump() if hasattr(facts, "model_dump") else str(facts), "method": extracted_by},
                        rule_applied="REJECT_LOW_CONFIDENCE",
                        source_citations=[],
                        timestamp=ticket.created_at
                    ))
            # ----------------------------------------
            
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
                    reason_code=f"CONTEXT_UNCERTAIN/UNKNOWN_CLIENT (Unregistered client with unknown SLA contract: '{ticket.client_name}')",
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
            allowed_evidence, rejected_evidence = self.store.search_evidence(ticket)
            
            # Log rejected evidence if any
            if rejected_evidence:
                audit_records.extend(rejected_evidence)
                logger.info(f"Rejected {len(rejected_evidence)} evidence snippets for cross-contamination", extra={"structured_data": {"ticket_id": ticket.ticket_id}})
                
            is_driver_safe, driver_action, driver_citations = self.rule_engine.evaluate_driver_safety(ticket)
            
            enrichment_citations = sorted(driver_citations) if not is_driver_safe else ["drivers_roster.csv", "fleet_master.csv"]
            if allowed_evidence:
                enrichment_citations.extend([f"FTS5: {e.source_file}" for e in allowed_evidence])
                
            audit_records.append(AuditEvent(
                event_id=f"AUD-{ticket.ticket_id}-02",
                ticket_id=ticket.ticket_id,
                step_number=2,
                step_name="CONTEXT_ENRICHMENT",
                decision=f"Enriched with driver {ticket.driver_id}, client {ticket.client_name}, vehicle {ticket.vehicle_reg_canonical}. Driver status: {driver_action}",
                input_data_summary={"client": ticket.client_name, "driver_id": ticket.driver_id, "origin": ticket.origin_hub},
                rule_applied="RULE_07_DRIVER_NIGHT_SOLO_RESTRICTION" if not is_driver_safe else "STANDARD_ENRICHMENT",
                source_citations=enrichment_citations,
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
                    reason_code="CONTEXT_UNCERTAIN/INSUFFICIENT_FLEET (No eligible replacement vehicle available)",
                    quarantined_at=ticket.created_at
                )
                quarantine_records.append(quarantine_entry)
                
                logger.warning("Insufficient fleet for ticket", extra={"structured_data": {
                    "ticket_id": ticket.ticket_id,
                    "stage": "ALLOCATE_REPLACEMENT",
                    "status": "QUARANTINED",
                    "quarantine_reason": "INSUFFICIENT_FLEET"
                }})
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

            logger.info("Replacement vehicle allocated", extra={"structured_data": {
                "ticket_id": ticket.ticket_id,
                "stage": "ALLOCATE_REPLACEMENT",
                "status": "SUCCESS",
                "decision": winner_vehicle.registration_canonical,
                "rule_id": "RULE_03_ORIGIN_PROXIMITY_50KM"
            }})

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
