# HYBRID CONTEXT RESOLUTION IMPLEMENTATION PLAN

## 1. CURRENT SYSTEM BASELINE
The system currently implements a deterministic pipeline consisting of ticket ingestion, PII scrubbing, normalization, ContextStore (SQLite), entity resolution, rule engine, allocator, and a Gemini perception fallback. All existing 29+ tests pass with bit-for-bit idempotency. The deterministic decision core is **FROZEN**. We are adding a Context Resolution / Evidence Retrieval layer strictly *between* perception and deterministic decision-making.

## 2. PROBLEM WE ARE SOLVING
Operational knowledge is distributed across structured and unstructured sources. Real emails lack explicit `TKT-XXXX` identifiers and instead use implicit references ("kal raat wali gaadi", "Shakti loads"), natural language, code-switching/Hinglish, and messy formats. We must resolve these implicit, unstructured references into verified, deterministic entities before the rule engine executes.

## 3. PRIMARY ARCHITECTURAL QUESTION
**Recommendation: Option E - Hybrid Retrieval (Structured + FTS + Optional Semantic Fallback + LLM Extraction + Deterministic Verification)**
* **Correctness:** Highest. Deterministic constraints prevent hallucinated linkages.
* **Complexity:** Moderate. We optimize for the actual 40-email dataset first using SQLite FTS5. We do not assume FTS5 can solve all semantic discovery; an optional semantic fallback is defined but no heavy Vector DB is committed.
* **Latency:** Low local retrieval latency.
* **Dependency Footprint:** Minimal (SQLite is built-in).
* **PII/Offline:** PII remains scrubbed before LLM. Retrieval is local.
* **Determinism:** High. FTS is deterministic; LLM is constrained to extraction.

**Evaluation Matrix: FTS-only vs FTS+Semantic Fallback**
(To be executed during Phase 7 Evaluation on a manual ground-truth set of 5-10 difficult real cases to decide if semantic retrieval is actually needed. We will compare correctness, not merely retrieval count.)
| Metric | FTS5-Only | FTS5 + Semantic Fallback |
| :--- | :--- | :--- |
| **Setup Cost** | Low (Built-in) | High (Requires embedding model/index) |
| **Determinism** | 100% | Approximate |
| **"Jugaad" discovery** | Expected to succeed via keywords | Expected to succeed |
| **Implicit concept ("that old truck")** | Likely to fail | Expected to succeed |
| **Decision** | **Implement First** | **Implement ONLY if FTS5 fails evaluation on Ground Truth** |

## 4. VECTOR SEARCH IS NOT ENTITY RESOLUTION
* **Retrieval:** FTS (or semantic fallback) finds emails mentioning "kal raat" or "jugaad".
* **Extraction:** Gemini parses the email to output: `{"time": "last night", "event": "breakdown repair"}`.
* **Entity Resolution:** Python logic queries SQLite: `SELECT vehicle FROM trips WHERE date = 'last night' AND event = 'breakdown'`.
* **Decision:** Rule Engine applies the "7-day jugaad restriction" to the resolved vehicle.
Retrieval and language understanding are strictly separated from entity resolution.

## 5. PROPOSED TARGET ARCHITECTURE
```text
                 TICKET
                    │
                    ▼
             PII SCRUBBING
                    │
                    ▼
          CANONICAL TICKET FACTS
                    │
                    ▼
          ┌─────────────────────┐
          │ CONTEXT RESOLUTION  │
          │                     │
          │ Structured Lookup   │
          │ Keyword Search(FTS) │
          │ (Semantic Fallback) │
          └──────────┬──────────┘
                     │
                     ▼
             CANDIDATE EVIDENCE
                     │
                     ▼
              GEMINI / NLP
                     │
                     ▼
             CANDIDATE FACTS
                     │
                     ▼
          ENTITY CORROBORATION
                     │
                     ▼
            VERIFIED CONTEXT
                     │
                     ▼
             DETERMINISTIC
              RULE ENGINE
                    ...
```

## 6. DATA INDEX DESIGN
* **Granularity:** Message-level chunking. Email threads are split into individual messages but retain a `thread_id` to preserve conversational context.
* **Metadata:** `source_file`, `message_id`, `timestamp`, `detected_client`, `detected_vehicle`, `scrubbed_content`.
* **Why:** Full threads dilute FTS relevance; sentence-level loses context. Message-level is the operational unit.

## 7. PII + INDEXING DESIGN
```text
RAW SOURCE
   ↓
PII SCRUB (pii_scrubber.py)
   ↓
SAFE TEXT
   ↓
SQLITE FTS VIRTUAL TABLE
```
* **Embeddings:** Evaluated only if FTS fails. If needed, they will be generated from safe, PII-scrubbed text.
* **External API:** Gemini receives ONLY PII-scrubbed text for extraction. Raw PII NEVER leaves the machine.

## 8. RETRIEVAL STRATEGY
1. **Stage 1 (Context-Dependent Candidate Narrowing):** Known fields (Date, Client, Hub) are used as soft ranking/boosting signals. Hard filters are applied ONLY when their presence is absolutely reliable to avoid eliminating potentially relevant documents prematurely.
2. **Stage 2 (Exact Lookup):** Match canonical vehicle/driver IDs directly.
3. **Stage 3 (FTS):** Search remaining filtered emails for operational keywords ("breakdown", "gate", "jugaad", "late").
4. **Stage 4 (Candidate Ranking):** Rank documents based on boosting signals, recency, and keyword density. Pass top 3 to extraction.
5. **Stage 5 (Semantic Fallback Activation):** Activate the optional semantic query if:
   * No candidate exists.
   * Candidates exist but evidence confidence is insufficient.
   * Candidates fail corroboration thresholds.

## 9. IMPLICIT REFERENCE RESOLUTION
```text
"kal raat wali gaadi"
        ↓
Gemini Extraction (Language Understanding ONLY: Time: "T-1 night", Subject: "vehicle")
        ↓
Candidate Identity (Query operational events for that night)
        ↓
Entity Corroboration (Cross-check hub/route/client constraints)
        ↓
Trusted entity? (Is it a Verified Entity?)
   YES        NO
    ↓          ↓
VERIFY      QUARANTINE
```

## 10. ENTITY RESOLUTION ENGINE
Replaces arbitrary scoring with an **Evidence-Class Corroboration Model**:

* **Class 1 (Authoritative):** Explicit canonical plate match (`UP17GN7381`) in the text.
* **Class 2 (Corroborated Identity):** Requires:
  * Implicit reference ("kal raat wali gaadi")
  * Temporal consistency
  * At least one independent contextual constraint (e.g., location, load, client)
  * Exactly ONE plausible entity found in the DB
  * Source evidence backing the contextual facts
* **Class 3 (Uncorroborated / Ambiguous):** Implicit reference but fails the Class 2 requirements (e.g., maps to multiple plausible vehicles, or missing contextual constraints).

Model confidence is NOT equated with identity truth. Only Class 1 and Class 2 evidence establishes a Verified Entity.

## 11. CONFIDENCE MODEL
* **Verified Entity:** Class 1 or Class 2 evidence. Proceeds to Rule Engine.
* **Ambiguous Contextual Reference:** Class 3 evidence.
* **Action:** Ambiguous references result in NO OPERATIONAL ACTION. The system immediately outputs a QUARANTINE record indicating that human review is required because entity identity could not be deterministically established.

## 12. GEMINI ROLE
* **DOES:** Fact extraction, Hinglish translation, temporal expression parsing.
* **DOES NOT:** Choose replacement vehicles, override SLAs, invent entities, or perform entity resolution.
* **Strict Separation:** LLM handles language understanding. Python handles logic and entity resolution.

## 13. HINGLISH / MULTILINGUAL DESIGN
```text
"Guddu ne gaadi jugaad se theek ki"
      ↓
Gemini NLP Extraction
      ↓
{"event_type": "temporary_repair", "mechanic": "Guddu", "constraint": "7_days"}
      ↓
Entity Corroboration (Which gaadi?)
      ↓
Rule Engine
```
Works for general code-switching by deferring semantic translation to Gemini, outputting standard English structured JSON.

## 14. SOURCE PRECEDENCE (SEPARATE FROM IDENTITY)
**Identity Evidence** (Evidence Class) measures confidence in identifying an entity.
**Source Authority** measures which source governs a particular fact/field. An explicit vehicle plate (Class 1) identifies the truck but does not make every field in that document authoritative over the DB.

Source precedence is **field-specific** and governed by: Field Type, Source Authority, Explicitness, and Recency.
Dispatcher communication can override structured configuration **ONLY** for fields explicitly defined as operationally mutable.

* **Immutable Fields (Structured DB Authority):** Vehicle Specs (Capacity, BS Stage).
* **Mutable Fields (Operationally Overrideable):**
  * **Maintenance Status:** Structured DB (`maintenance_log.xlsx`) is primary, but a recent **Dispatcher Email** explicitly reporting a roadside `jugaad` fix takes precedence due to recency and operational authority.
  * **SLA Constraints:** Client Contract is primary, but an explicit **Dispatcher Directive** noting an internal operational reality (e.g., "Shakti is 36 hours internally") overrides the standard contract.
* **General Rule:** There is NO universal "recent email always wins" rule.

## 15. PROVENANCE DESIGN
Every fact passed to the Rule Engine is wrapped in an `EvidenceContext`:
```python
@dataclass
class EvidenceContext:
    fact_value: Any
    retrieval_method: str # "FTS5" or "Semantic"
    sanitized_retrieval_reason: str # E.g., query fingerprint
    retrieval_score: float
    source_citation: str
    extraction_method: str # "Gemini-3.6"
    evidence_class: int # 1, 2, or 3
    corroboration_details: str
```
Sensitive raw query text is omitted to maintain safety.

## 16. CROSS-CONTAMINATION DEFENSE
* **Defense:** Context-dependent candidate narrowing (Client/Date boosting) BEFORE full search.
* An Apex email will score significantly lower for a Shakti ticket because the SQLite ranking explicitly penalizes mismatches in `client_name` or temporal distance.

## 17. TKT-0027 TARGET WALKTHROUGH
**Implementation Target:** We aim to prove if a linkage exists between TKT-0027 and unstructured evidence like `thread_25_internal_jugaad.txt`. We do NOT assume it is relevant until retrieved and corroborated.

**Target Flow:**
```text
TKT-0027
 ↓
Retrieve candidate evidence (Query FTS5 using ticket context keywords)
 ↓
Extract facts (Gemini parses unstructured candidate texts)
 ↓
Corroborate (Python engine checks Candidate Identities against operational events)
 ↓
Verify (Does the evidence meet Class 1 or Class 2 thresholds?)
     ↙                      ↘
Verified Context        Quarantine (Ambiguous/Uncorroborated)
```

## 18. EXAMPLE END-TO-END SCENARIOS
* **Scenario A (Clean Ticket):** No relevant evidence retrieved -> Missing context is not required for a safe decision -> Proceed with standard deterministic rules.
* **Scenario B (Unstructured English):** FTS retrieves -> Gemini extracts constraints -> Corroboration -> Rule engine.
* **Scenario C (Hinglish):** FTS retrieves -> Gemini translates/extracts -> Corroboration -> Rule engine.
* **Scenario D (Implicit):** FTS retrieves -> Gemini extracts time -> DB temporal join -> Class 2 Corroboration -> Verified Entity.
* **Scenario E (Conflicting):** Gemini extracts SLA change -> Dispatcher email overrides client contract (Field-Specific Precedence) -> Rule engine.

## 19. FAILURE SCENARIOS
* **No relevant evidence:** Proceed only when the missing context is not required for a safe decision. If missing evidence is strictly required for safety/action -> QUARANTINE / HUMAN_REVIEW.
* **Ambiguous vehicle (Class 3):** Ambiguous Reference -> QUARANTINE.
* **Gemini unavailable:** Fallback to safe defaults / QUARANTINE if safety critical.

## 20. TECHNOLOGY SELECTION
**Recommended:** **SQLite FTS5** first.
* Optimize for the 40-email dataset.
* Zero dependencies, zero network risk for retrieval. 100% local, PII-safe.
* If FTS5 demonstrably fails to retrieve implicit contexts during Phase 7 evaluation, we will implement a semantic fallback. We do NOT commit to a vector database at this stage.

## 21. DETERMINISM / IDEMPOTENCY
* SQLite FTS is bit-for-bit deterministic.
* Gemini extraction is pseudo-deterministic (`temperature=0`, strict JSON schema).
* Corroboration logic is strict and exact.

## 22. TESTING PLAN
* **Retrieval Eval Ground Truth:** Create a manual eval set of 5-10 difficult cases (ticket, expected source, FTS result, semantic result if tested, true relevance, corroboration status).
* **Entity Res:** Corroboration tests for Class 1 vs Class 2 vs Class 3 (Quarantine).
* **Language:** LLM parsing Hinglish WITHOUT injecting entity IDs.
* **Safety:** PII scrubbing before LLM.
* **Regression:** Existing 29+ tests MUST pass.

## 23. MIGRATION / IMPLEMENTATION PHASES
* **Phase 0:** Baseline freeze. Rule engine and allocator remain absolutely untouched.
* **Phase 1:** SQLite FTS5 setup & ingestion pipeline (PII scrub -> index emails).
* **Phase 2:** Entity Corroboration scoring logic (Classes 1-3).
* **Phase 3:** Connect Gemini for extraction of FTS results.
* **Phase 4:** Integrate `EvidenceContext` into `pipeline.py`.
* **Phase 5:** Implement field-specific source precedence overriding logic.
* **Phase 6:** Semantic Fallback (Optional, implemented ONLY if Phase 7 shows FTS5 failure).
* **Phase 7:** Evaluation against Ground Truth & FTS vs Semantic Matrix generation.

## 24. FILE-LEVEL CHANGE PLAN
| Phase | File | Change | Why | Risk | Tests |
| ----- | ---- | ------ | --- | ---- | ----- |
| 1 | `src/context_store.py` | Add FTS5 table & email ingestion | Index unstructured data | Low | `test_fts_index()` |
| 2/5 | `src/context_store.py` | Add `corroborate_entity()` & precedence logic | Verification & Overrides | Med | `test_corroboration()` |
| 3 | `src/llm_adapter.py` | Add `extract_context_from_document()` | Parse Hinglish/implicit facts | Low | `test_context_extract()` |
| 4 | `src/pipeline.py` | Wire FTS+LLM step before rule engine | Connect resolution layer | High | `test_end_to_end()` |

## 25. NEW FILES
* No new files required. `context_store.py` and `llm_adapter.py` naturally own these responsibilities.

## 26. EXISTING FILES THAT MUST REMAIN UNCHANGED
* `src/rule_engine.py` (Core logic frozen)
* `src/allocator.py` (Allocation logic frozen)
* `src/pii_scrubber.py` (Existing scrubbing logic frozen)

## 27. DEPENDENCY PLAN
* **None.** Built-in `sqlite3` (with FTS5) and existing `google-genai` SDK.

## 28. API KEY PLAN
* **Existing `GEMINI_API_KEY` only.** No external vector DB keys needed.

## 29. OBSERVABILITY
* `pipeline.py` audit trail extended with `AUD-{ticket}-CTX`. Replace logging Gemini raw output with logging a sanitized structured extraction summary (provider, extracted field names, validation status, extraction method, source citation, evidence class, corroboration result). Raw prompts/responses are never stored unless required for private local debug artifacts.

## 30. PERFORMANCE BUDGET
* **Clean ticket:** 0 Gemini calls.
* **Ambiguous ticket:** 1 Gemini call (batch processing top 3 FTS hits).
* **Latency:** Target latency <2s for local retrieval; Gemini/API latency measured separately.

## 31. SECURITY MODEL
* Emails pass through `PIIScrubber` *before* being inserted into FTS and *before* being sent to Gemini.
* No LLM output directly triggers an action without Evidence Corroboration.

## 32. ACCEPTANCE CRITERIA
* 29/29 existing tests pass.
* If the supplied data contains sufficient independent evidence, the system must deterministically corroborate the contextual reference; otherwise it must safely quarantine as ambiguous/insufficient data.
* No PII leakage in logs.

## 33. DEMO PLAN
* **Demo 1:** Standard TKT (Zero Gemini).
* **Demo 2:** TKT-0027 + `thread_25` (Demo will show ACTUAL result, whether corroborated or quarantined). System must discover and corroborate without predefined assumption.
* **Demo 3:** Explainability. Show the `EvidenceContext` JSON with Evidence Class 2 and field-specific overrides.

## 34. ARCHITECTURAL DIFFERENTIATOR
Unlike standard RAG, this architecture isolates **AI for perception/extraction**, uses **FTS/Semantic fallback strictly for retrieval**, and leverages a **Class-Based Corroboration Model** to verify identities and manage field-specific overrides deterministically.

## 35. FINAL RECOMMENDATION
* **Recommended Architecture:** SQLite FTS5 + Gemini Extraction + Python Evidence Corroboration (with optional Semantic Fallback).
* **Why This Is the Best Fit:** Prioritizes the 40-email hackathon dataset first, avoids vector DB bloat, and rigorously defends against hallucinated entity resolution through evidence classes.
* **What We Should NOT Build:** An immediate semantic search vector index before proving FTS5 fails.
* **What We Should Build First:** SQLite FTS indexing for scrubbed emails and the Corroboration Model.
* **What We Should Defer:** Semantic search, pending the Phase 7 evaluation matrix.
