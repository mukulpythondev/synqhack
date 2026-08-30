from enum import Enum
from typing import Optional, List, Dict
from src.models import AuditEvent
from datetime import datetime

class EvidenceScope(Enum):
    GLOBAL = "GLOBAL"
    CLIENT_SPECIFIC = "CLIENT_SPECIFIC"
    ENTITY_SPECIFIC = "ENTITY_SPECIFIC"

class EvidenceFilter:
    @staticmethod
    def classify_scope(text: str) -> tuple[EvidenceScope, Optional[str]]:
        text_lower = text.lower()
        if "dispatcher policy" in text_lower or "global" in text_lower or "all clients" in text_lower:
            return EvidenceScope.GLOBAL, None
            
        for client in ["Apex Chemicals", "Shakti Cement", "Vertex Retail", "Orion Pharma"]:
            if client.lower() in text_lower:
                return EvidenceScope.CLIENT_SPECIFIC, client
                
        return EvidenceScope.GLOBAL, None

    @staticmethod
    def filter_candidates(ticket_id: str, ticket_client: str, candidates: List[Dict[str, str]]) -> tuple[List[Dict[str, str]], List[AuditEvent]]:
        """
        Filters evidence candidates. 
        candidates expected format: [{'id': 'doc1', 'text': '...', 'source': '...'}]
        """
        allowed = []
        audit_records = []
        
        for cand in candidates:
            scope, evidence_client = EvidenceFilter.classify_scope(cand['text'])
            
            is_compatible = True
            reason = ""
            
            if scope == EvidenceScope.CLIENT_SPECIFIC:
                if ticket_client and ticket_client.strip() and ticket_client.upper() != "UNKNOWN":
                    if evidence_client and evidence_client != ticket_client:
                        is_compatible = False
                        reason = f"Rejected CLIENT_SPECIFIC evidence for {evidence_client} (Incompatible with ticket client {ticket_client})"
            
            if is_compatible:
                allowed.append(cand)
            else:
                audit_records.append(AuditEvent(
                    event_id=f"AUD-{ticket_id}-CTX-REJ-{cand['id']}",
                    ticket_id=ticket_id,
                    step_number=1,
                    step_name="CROSS_CONTAMINATION_FILTER",
                    decision=reason,
                    input_data_summary={"candidate_id": cand['id'], "ticket_client": ticket_client},
                    rule_applied="RULE_CLIENT_BOUNDARY",
                    source_citations=[cand.get('source', 'unknown')],
                    timestamp=cand.get('timestamp', '')
                ))
                
        return allowed, audit_records
