"""
Meridian Freight Breakdown Automation
Optional Isolated Gemini Perception & Language Understanding Layer

ARCHITECTURAL PRINCIPLE:
- GEMINI = PERCEPTION / UNSTRUCTURED FACT EXTRACTION
- DETERMINISTIC CODE = AUTHORITY (Rules, Allocations, Serialization)
- HUMAN = IRREVERSIBLE ACTION AUTHORIZATION

The deterministic core remains 100% operational without Gemini.
"""

import os
import re
import json
import logging
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
from pydantic import BaseModel, Field

# Load .env file if available (without hardcoding or printing secrets)
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

from src.pii_scrubber import PIIScrubber
from src.normalizer import normalize_vehicle_reg, normalize_client_name

logger = logging.getLogger("MeridianPerception")

# =====================================================================
# Strict Pydantic Perception Schema
# =====================================================================

class PerceptionFacts(BaseModel):
    """
    Strictly extracted facts from unstructured text.
    Extractor model must never make operational decisions or invent missing data.
    """
    vehicle_reg: Optional[str] = Field(default=None, description="Extracted vehicle registration plate")
    client: Optional[str] = Field(default=None, description="Extracted client/customer name")
    driver_id: Optional[str] = Field(default=None, description="Extracted driver ID (e.g. DRV-001)")
    incident_date: Optional[str] = Field(default=None, description="Extracted date of event (YYYY-MM-DD)")
    event_type: Optional[str] = Field(default=None, description="Type of event: breakdown, delay, gate_closure, maintenance")
    repair_status: Optional[str] = Field(default=None, description="Status of repair: completed, pending, temporary")
    brake_work: Optional[bool] = Field(default=None, description="True if brake repair or pad replacement occurred")
    temporary_repair: Optional[bool] = Field(default=None, description="True if roadside temporary patch/jugaad occurred")
    route_reference: Optional[str] = Field(default=None, description="Route or location mentioned (e.g. Lucknow, Rudrapur)")
    confidence: float = Field(default=0.0, description="Extraction confidence score between 0.0 and 1.0")
    evidence_spans: List[str] = Field(default_factory=list, description="Verbatim text snippets supporting the facts")
    extraction_notes: Optional[str] = Field(default=None, description="Brief note on extraction without ungrounded assumptions")


class SchemaMappingProposal(BaseModel):
    """
    Structured proposal for an unrecognized JSON key.
    """
    proposed_canonical_key: Optional[str] = Field(default=None, description="Proposed canonical key from whitelist")
    confidence: float = Field(default=0.0, description="Confidence score")


class QueryIntent(BaseModel):
    """
    Structured query intent for conversational QA fallback.
    """
    target_entity_type: Optional[str] = Field(default=None, description="Type of entity: vehicle, client, corridor, rule")
    entity_identifier: Optional[str] = Field(default=None, description="Identifier: e.g. UP37UP7482, Shakti Cement, Delhi NCR")
    intent_topic: Optional[str] = Field(default=None, description="Topic: sla, gate_curfew, vehicle_rotation, winter_bs6, hill_route, status")


# Whitelist of allowed canonical ticket fields
ALLOWED_CANONICAL_KEYS = {
    "ticket_id",
    "vehicle",
    "driver_id",
    "origin_hub",
    "destination",
    "km_from_origin_hub",
    "issue",
    "severity",
    "client",
    "created_at"
}


# =====================================================================
# Perception Provider Interface
# =====================================================================

class PerceptionProvider(ABC):
    """
    Abstract interface for perception and fact extraction.
    """

    @abstractmethod
    def extract_unstructured_facts(self, text: str) -> PerceptionFacts:
        pass

    @abstractmethod
    def propose_schema_mapping(self, unrecognized_key: str, sample_value: Any) -> Optional[str]:
        pass

    @abstractmethod
    def interpret_query_intent(self, query_text: str) -> Optional[QueryIntent]:
        pass


# =====================================================================
# 1. Deterministic Perception (Primary Choice)
# =====================================================================

class DeterministicPerception(PerceptionProvider):
    """
    Deterministic rule-based extractor using regex and canonical normalizers.
    Always executed first.
    """

    PLATE_REGEX = re.compile(r'\b[A-Z]{2}[-\s]?[0-9]{1,2}[-\s]?[A-Z]{1,3}[-\s]?[0-9]{3,4}\b', re.IGNORECASE)
    DATE_REGEX = re.compile(r'\b(\d{4}-\d{2}-\d{2}|\d{1,2}\s+[A-Za-z]+\s+\d{4})\b')
    DRIVER_REGEX = re.compile(r'\bDRV-\d{3,4}\b', re.IGNORECASE)

    def extract_unstructured_facts(self, text: str) -> PerceptionFacts:
        facts = PerceptionFacts()
        spans = []

        # 1. Vehicle Registration
        plate_match = self.PLATE_REGEX.search(text)
        if plate_match:
            raw_reg = plate_match.group(0)
            canon_reg, is_valid = normalize_vehicle_reg(raw_reg)
            if is_valid:
                facts.vehicle_reg = canon_reg
                spans.append(raw_reg)

        # 2. Driver ID
        drv_match = self.DRIVER_REGEX.search(text)
        if drv_match:
            facts.driver_id = drv_match.group(0).upper()
            spans.append(drv_match.group(0))

        # 3. Client Name
        text_lower = text.lower()
        for cname in ["Shakti Cement", "Vertex Retail", "Apex Chemicals", "Orion Pharma"]:
            if cname.lower() in text_lower or cname.split()[0].lower() in text_lower:
                facts.client = cname
                spans.append(cname)
                break

        # 4. Date
        date_match = self.DATE_REGEX.search(text)
        if date_match:
            facts.incident_date = date_match.group(0)
            spans.append(date_match.group(0))

        # 5. Brake & Jugaad keywords
        if any(k in text_lower for k in ["brake", "pad", "drum"]):
            facts.brake_work = True
        if any(k in text_lower for k in ["jugaad", "temporary", "temp fix"]):
            facts.temporary_repair = True

        facts.evidence_spans = spans
        # Compute deterministic confidence
        if facts.vehicle_reg and (facts.client or facts.driver_id):
            facts.confidence = 0.95
        elif facts.vehicle_reg or facts.client:
            facts.confidence = 0.70
        else:
            facts.confidence = 0.20

        return facts

    def propose_schema_mapping(self, unrecognized_key: str, sample_value: Any) -> Optional[str]:
        # Deterministic aliases handled in DynamicTicketAdapter
        return None

    def interpret_query_intent(self, query_text: str) -> Optional[QueryIntent]:
        q_lower = query_text.lower()
        intent = QueryIntent()

        # Check vehicle
        plate_match = self.PLATE_REGEX.search(query_text)
        if plate_match:
            canon_reg, is_valid = normalize_vehicle_reg(plate_match.group(0))
            if is_valid:
                intent.target_entity_type = "vehicle"
                intent.entity_identifier = canon_reg
                intent.intent_topic = "status"
                return intent

        # Check client
        for cname in ["shakti", "vertex", "apex", "orion"]:
            if cname in q_lower:
                intent.target_entity_type = "client"
                intent.entity_identifier = cname.title()
                if "sla" in q_lower or "hour" in q_lower:
                    intent.intent_topic = "sla"
                elif "gate" in q_lower or "curfew" in q_lower:
                    intent.intent_topic = "gate_curfew"
                elif "rotation" in q_lower:
                    intent.intent_topic = "vehicle_rotation"
                return intent

        return None


# =====================================================================
# 2. Gemini Perception (Optional Isolated Fallback)
# =====================================================================

class GeminiPerception(PerceptionProvider):
    """
    Gemini 2.5 Flash perception adapter using official google-genai SDK.
    Activated ONLY when deterministic perception is ambiguous or low-confidence.
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        if api_key is not None:
            self.api_key = api_key if api_key != "" else None
        else:
            self.api_key = os.getenv("GEMINI_API_KEY")

        self.model_name = model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.client = None

        if self.api_key:
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logger.warning(f"Failed to initialize google-genai client: {e}")
                self.client = None

    @property
    def is_available(self) -> bool:
        return self.client is not None

    def extract_unstructured_facts(self, text: str) -> PerceptionFacts:
        """
        Extracts structured facts from unstructured text using Gemini.
        Pre-scrubs all personal data before dispatch.
        """
        if not self.is_available:
            return PerceptionFacts(confidence=0.0, extraction_notes="Gemini unavailable (no API key or client error)")

        # PII Boundary: Strict Pre-Ingestion Scrubbing
        sanitized_prompt_text = PIIScrubber.scrub_text(text)

        system_instruction = (
            "You are a strict factual perception extractor for a freight transportation system. "
            "Extract ONLY information explicitly present in the provided text. "
            "Never invent missing values. Use null for unknown fields. "
            "Never infer an operational decision, never recommend a vehicle, never invent an SLA or business rule. "
            "Never output personal data (phones, Aadhaar, driving licenses, full names). "
            "Return structured JSON matching the PerceptionFacts schema."
        )

        try:
            from google.genai import types
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_text(text=f"{system_instruction}\n\nTEXT TO EXTRACT:\n\"\"\"{sanitized_prompt_text}\"\"\"")
                        ]
                    )
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=PerceptionFacts,
                    temperature=0.0, # Zero temperature for maximum deterministic stability
                )
            )

            if response and response.text:
                data = json.loads(response.text)
                facts = PerceptionFacts.model_validate(data)
                return facts
        except Exception as e:
            logger.warning(f"Gemini unstructured extraction failed safely: {e}")

        return PerceptionFacts(confidence=0.0, extraction_notes="Gemini extraction error or invalid response")

    def propose_schema_mapping(self, unrecognized_key: str, sample_value: Any) -> Optional[str]:
        """
        Proposes a canonical key for an unrecognized column name.
        Result is strictly validated against ALLOWED_CANONICAL_KEYS.
        """
        if not self.is_available:
            return None

        prompt = (
            f"Given an unrecognized freight data column name '{unrecognized_key}' with sample value '{sample_value}', "
            f"map it to the best matching canonical field from this strict whitelist: {sorted(list(ALLOWED_CANONICAL_KEYS))}. "
            "If no reasonable match exists, return proposed_canonical_key as null. "
            "Return structured JSON matching SchemaMappingProposal."
        )

        try:
            from google.genai import types
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=SchemaMappingProposal,
                    temperature=0.0,
                )
            )
            if response and response.text:
                data = json.loads(response.text)
                proposal = SchemaMappingProposal.model_validate(data)
                if proposal.proposed_canonical_key in ALLOWED_CANONICAL_KEYS and proposal.confidence >= 0.7:
                    return proposal.proposed_canonical_key
        except Exception as e:
            logger.warning(f"Gemini schema mapping proposal failed safely: {e}")

        return None

    def interpret_query_intent(self, query_text: str) -> Optional[QueryIntent]:
        """
        Interprets natural language question intent into safe structured query parameters.
        Does NOT answer the question itself; answers are retrieved locally from verified ContextStore.
        """
        if not self.is_available:
            return None

        sanitized_query = PIIScrubber.scrub_text(query_text)
        prompt = (
            f"Analyze this operational query: '{sanitized_query}'. "
            "Extract target entity type (vehicle, client, corridor, rule), entity identifier, and intent topic. "
            "Never generate an answer. Extract intent parameters only. "
            "Return structured JSON matching QueryIntent."
        )

        try:
            from google.genai import types
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=QueryIntent,
                    temperature=0.0,
                )
            )
            if response and response.text:
                data = json.loads(response.text)
                return QueryIntent.model_validate(data)
        except Exception as e:
            logger.warning(f"Gemini query intent interpretation failed safely: {e}")

        return None


# =====================================================================
# 3. Perception Router (Deterministic First, Gemini Fallback)
# =====================================================================

class PerceptionRouter:
    """
    Coordinates PerceptionProviders.
    Enforces deterministic-first execution: Gemini is called ONLY if
    deterministic extraction confidence is below threshold (< 0.8).
    """

    def __init__(self, gemini_provider: Optional[GeminiPerception] = None):
        self.deterministic = DeterministicPerception()
        self.gemini = gemini_provider or GeminiPerception()

    @property
    def status_diagnostic(self) -> str:
        if self.gemini.is_available:
            return f"LLM Perception: ENABLED (Model: {self.gemini.model_name})"
        return "LLM Perception: DETERMINISTIC-ONLY (No API Key)"

    def extract_facts(self, text: str, context_source: str = "") -> Tuple[PerceptionFacts, str]:
        """
        Extracts facts with fallback.
        Returns: (facts, provider_used: 'deterministic' | 'gemini')
        """
        # Step 1: Attempt Deterministic Perception
        det_facts = self.deterministic.extract_unstructured_facts(text)
        if det_facts.confidence >= 0.80:
            return det_facts, "deterministic"

        # Step 2: Fallback to Gemini if available and text is ambiguous
        if self.gemini.is_available:
            gem_facts = self.gemini.extract_unstructured_facts(text)
            if gem_facts.confidence > det_facts.confidence:
                return gem_facts, "gemini"

        return det_facts, "deterministic"

    def resolve_schema_key(self, raw_key: str, sample_value: Any) -> Optional[str]:
        """
        Resolves unrecognized schema keys with optional Gemini proposal.
        """
        if self.gemini.is_available:
            proposal = self.gemini.propose_schema_mapping(raw_key, sample_value)
            if proposal in ALLOWED_CANONICAL_KEYS:
                return proposal
        return None
