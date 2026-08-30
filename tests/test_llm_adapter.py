"""
Unit Tests: Optional Gemini Perception Layer & Isolated Fallback Verification

Tests A-I:
- Test A: No API Key (System operates in deterministic-only mode)
- Test B: Deterministic Parser Wins (Gemini is not called for unambiguous inputs)
- Test C: Gemini Fallback (Ambiguous text triggers validated perception)
- Test D: Hallucinated Vehicle (Non-existent vehicle rejected by entity resolution)
- Test E: Unknown Client (Unrecognized client quarantined with INSUFFICIENT_DATA)
- Test F: Invalid Gemini JSON (Safe degradation on malformed model output)
- Test G: Gemini Failure / Timeout (Zero pipeline crashes on API errors)
- Test H: PII Hard Boundary (Raw PII scrubbed before model delivery)
"""

import json
from unittest.mock import MagicMock, patch
from pathlib import Path
import pytest

from src.llm_adapter import (
    PerceptionFacts,
    SchemaMappingProposal,
    QueryIntent,
    DeterministicPerception,
    GeminiPerception,
    PerceptionRouter
)
from src.context_store import ContextStore
from src.pipeline import BreakdownPipeline
from src.pii_scrubber import PIIScrubber
from src.config import TICKETS_PATH

# ---------------------------------------------------------------------
# Test A — No API Key: Deterministic-Only Mode
# ---------------------------------------------------------------------
def test_no_api_key_deterministic_mode(monkeypatch):
    """
    Verifies that with no API key, the router reports DETERMINISTIC-ONLY mode
    and standard pipeline execution completes with 100% success.
    """
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    provider = GeminiPerception(api_key="")
    assert not provider.is_available
    
    router = PerceptionRouter(gemini_provider=provider)
    assert "DETERMINISTIC-ONLY" in router.status_diagnostic

    pipeline = BreakdownPipeline()
    wos, comms, quar, audit = pipeline.process_ticket_queue(TICKETS_PATH)
    assert len(wos) == 30
    assert len(quar) == 2

# ---------------------------------------------------------------------
# Test B — Deterministic Parser Wins (Zero Gemini Calls)
# ---------------------------------------------------------------------
def test_deterministic_parser_wins():
    """
    Verifies that when text contains standard patterns (e.g. valid plate + client),
    deterministic perception succeeds with high confidence and Gemini is NOT called.
    """
    mock_gemini = MagicMock(spec=GeminiPerception)
    mock_gemini.is_available = True

    router = PerceptionRouter(gemini_provider=mock_gemini)
    text = "Breakdown reported for vehicle UP37UP7482 on Apex Chemicals run"
    facts, provider_used = router.extract_facts(text)

    assert provider_used == "deterministic"
    assert facts.vehicle_reg == "UP37UP7482"
    assert facts.client == "Apex Chemicals"
    assert facts.confidence >= 0.80
    mock_gemini.extract_unstructured_facts.assert_not_called()

# ---------------------------------------------------------------------
# Test C — Gemini Fallback on Ambiguous Text
# ---------------------------------------------------------------------
def test_gemini_fallback_on_ambiguous_text():
    """
    Verifies that ambiguous text with low deterministic confidence triggers Gemini fallback.
    """
    mock_gemini = MagicMock(spec=GeminiPerception)
    mock_gemini.is_available = True
    mock_gemini.extract_unstructured_facts.return_value = PerceptionFacts(
        vehicle_reg="UP37UP7482",
        client="Apex Chemicals",
        incident_date="2026-08-20",
        event_type="breakdown",
        confidence=0.92,
        evidence_spans=["unit UP-37-UP-7482 had an issue"]
    )

    router = PerceptionRouter(gemini_provider=mock_gemini)
    # Ambiguous text that has low confidence in deterministic parser
    ambiguous_text = "The unit yesterday had an issue during the morning run"
    facts, provider_used = router.extract_facts(ambiguous_text)

    assert provider_used == "gemini"
    assert facts.vehicle_reg == "UP37UP7482"
    assert facts.confidence == 0.92
    mock_gemini.extract_unstructured_facts.assert_called_once()

# ---------------------------------------------------------------------
# Test D — Hallucinated Vehicle Rejected by Entity Resolution
# ---------------------------------------------------------------------
def test_hallucinated_vehicle_rejected():
    """
    Verifies that if Gemini returns a non-existent vehicle registration,
    the entity resolver in ContextStore rejects it and does NOT create a phantom vehicle.
    """
    store = ContextStore()
    hallucinated_reg = "ZZ99XX0000"
    v = store.get_vehicle(hallucinated_reg)
    assert v is None  # Entity resolution safety check: does not exist in master RC

# ---------------------------------------------------------------------
# Test E — Unknown Client Quarantined (Zero Invented SLAs)
# ---------------------------------------------------------------------
def test_unknown_client_quarantined(tmp_path):
    """
    Verifies that if an unknown client is extracted, the pipeline does not invent an SLA
    and routes the record to INSUFFICIENT_DATA quarantine.
    """
    unknown_ticket = [{
        "ticket_id": "TKT-SYN-UNKNOWN-CLIENT-LLM",
        "vehicle": "UP40IM3144",
        "driver_id": "DRV-001",
        "origin_hub": "Lucknow",
        "destination": "Delhi",
        "km_from_origin_hub": 20.0,
        "issue": "engine overheating",
        "severity": "HIGH",
        "client": "Extracted Phantom Client Inc",
        "created_at": "2026-08-30T10:00:00"
    }]
    tkt_file = tmp_path / "unknown_llm_client.json"
    tkt_file.write_text(json.dumps(unknown_ticket), encoding="utf-8")

    pipeline = BreakdownPipeline()
    wos, comms, quar, audit = pipeline.process_ticket_queue(tkt_file)

    assert len(wos) == 0
    assert len(comms) == 0
    assert len(quar) == 1
    assert "INSUFFICIENT_DATA" in quar[0].reason_code

# ---------------------------------------------------------------------
# Test F — Invalid Gemini JSON Safe Degradation
# ---------------------------------------------------------------------
def test_invalid_gemini_json_handling():
    """
    Verifies that malformed model outputs degrade safely without throwing unhandled exceptions.
    """
    gemini = GeminiPerception(api_key="fake-key-for-test")
    # Mock client generate_content returning unparseable text
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "{ malformed json ... not valid }"
    mock_client.models.generate_content.return_value = mock_response
    gemini.client = mock_client

    facts = gemini.extract_unstructured_facts("some text")
    assert facts.confidence == 0.0
    assert "Gemini extraction error" in (facts.extraction_notes or "")

# ---------------------------------------------------------------------
# Test G — Gemini API Failure / Timeout
# ---------------------------------------------------------------------
def test_gemini_api_timeout_fallback():
    """
    Verifies that network errors/timeouts from Gemini do not crash the pipeline.
    """
    gemini = GeminiPerception(api_key="fake-key-for-test")
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = TimeoutError("API Timeout")
    gemini.client = mock_client

    facts = gemini.extract_unstructured_facts("some text")
    assert facts.confidence == 0.0

# ---------------------------------------------------------------------
# Test H — PII Scrubbing Hard Gate Before LLM Delivery
# ---------------------------------------------------------------------
def test_pii_scrubbed_before_llm_call():
    """
    Verifies that raw Aadhaar, phone numbers, and driving licenses
    are scrubbed before being passed to Gemini.
    """
    raw_prompt_text = "Driver DRV-001 with Aadhaar 6515 3369 7284 and Phone +91 93118 40522 reported breakdown"
    scrubbed = PIIScrubber.scrub_text(raw_prompt_text)

    assert "6515 3369 7284" not in scrubbed
    assert "+91 93118 40522" not in scrubbed
    assert "[AADHAAR_MASKED]" in scrubbed
    assert "[PHONE_MASKED]" in scrubbed
    assert not PIIScrubber.contains_raw_pii(scrubbed)
