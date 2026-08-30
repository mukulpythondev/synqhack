# Meridian Freight: Breakdown-to-Resolution Automation System
### Production-Grade Enterprise Automation | Forward Deployed Engineering System

---

## 1. Quickstart (One Documented Command)

To run the complete breakdown-to-resolution automation on a clean machine:

```bash
python run_pipeline.py --eval-mode
```

* In **interactive production mode** (prompts human dispatcher for message authorization):
  ```bash
  python run_pipeline.py
  ```
* To process a custom or surprise ticket file:
  ```bash
  python run_pipeline.py --input path/to/surprise_tickets.json --eval-mode
  ```

---

## 2. Standard Output Deliverables

The system produces standard JSONL files in `outputs/` and `audit/`:

| Output File | Record Count | Description |
| :--- | :--- | :--- |
| `outputs/work_orders.jsonl` | 30 | Exactly one work order per unique valid ticket with citations and assigned replacement vehicle. |
| `outputs/comms_pending.jsonl` | 30 | Drafted client communications with full reasoning and citations for human sign-off. |
| `outputs/comms_sent.jsonl` | 30 | Dispatched communications recorded post-approval with zero raw personal data. |
| `outputs/quarantine.jsonl` | 2 | Malformed / broken tickets quarantined with explicit reason codes (`TKT-9101`, `TKT-9102`). |
| `audit/audit.jsonl` | 125 | Step-by-step decision log: input data, rules applied, citations, timestamps. |

---

## 3. Evaluator Inspection & Grounded QA Tools

### 3.1 30-Second Ticket Decision Trace Inspector
Reconstruct any ticket's full lifecycle, applied rules, replacement allocation, and citations:
```bash
python inspect_ticket.py TKT-0027
```
* Or inspect a quarantined record:
  ```bash
  python inspect_ticket.py TKT-9102
  ```

### 3.2 Grounded Context Query Interface
Ask natural language questions on operational rules, client SLAs, and conflict resolutions:
```bash
python query_context.py "What is the delivery SLA for Shakti Cement?"
python query_context.py "Why is vehicle RJ43DD3546 not eligible for Orion Pharma?"
python query_context.py "What are the rules for hill routes in winter?"
```

---

## 4. Architectural Highlights & Invariants

1. **Deterministic Idempotency (Zero Drift):**
   * Running `python run_pipeline.py` consecutively produces **100% bit-for-bit identical outputs**.
   * Identifiers are derived deterministically; zero reliance on `datetime.now()` in serialized outboxes.
2. **Hard Gate Defense (Zero Raw PII):**
   * Raw Aadhaar (`\d{4} \d{4} \d{4}`), 10-digit Indian phone numbers, driving licenses, and personal driver names are scrubbed at the private ingestion boundary.
   * Drivers are identified strictly by canonical ID (`DRV-XXX`).
   * Automated pre-write validator blocks any unmasked PII pattern before disk serialization.
3. **High-Fidelity Dispatcher Rule Engine:**
   * **Delhi NCR Winter BS6:** Oct–Feb restriction strictly enforces BS6 on corridors touching Delhi/NCR.
   * **Hill Routes (Rudrapur/Nainital):** Nov–Feb restriction requires Engine Heater = Yes and zero brake work in preceding 30 days.
   * **50km Origin Rule:** Breakdowns $\le 50\text{ km}$ from origin hub strictly mandate origin hub dispatch.
   * **Client SLAs:** Shakti 36h operational limit (overriding 48h contract); Vertex 6 PM gate curfew (scheduled morning 8 AM delivery); Apex vehicle rotation rule; Orion 2020+ RC year requirement.
   * **Guddu Jugaad:** 7-day clock with home-region confinement.
   * **Driver Safety:** Drivers $< 180\text{ days}$ tenure prohibited from solo night runs.
4. **Decoupled 4-Tier Replacement Allocation:**
   * Phase 1: Determine Allowed Hubs ($\le 50\text{ km}$ origin vs nearest by road distance).
   * Phase 2: Filter hard constraints (BS6, Heaters, Brakes, Jugaad, Status).
   * Phase 3: Rank by Distance $\rightarrow$ Capacity $\rightarrow$ Model Year $\rightarrow$ Alphabetical plate tie-breaker.
   * Phase 4: Full "Why Not" explanation matrix logged for all non-selected vehicles.
5. **Dynamic Surprise File Resilience:**
   * Dynamic alias adapter maps schema drifts seamlessly without pipeline crash.

---

## 5. Automated Verification Test Suite

Run the full automated test suite:
```bash
python -m pytest tests/ -v
```

* `tests/test_idempotency.py`: Validates deduplication and bit-for-bit identical hashes across 2 consecutive runs.
* `tests/test_quarantine.py`: Validates quarantine of `TKT-9101`, `TKT-9102`, unregistered clients (`INSUFFICIENT_DATA`), and edge-case payloads.
* `tests/test_rules.py`: Validates all 9 Dispatcher tribal knowledge rules (NCR winter BS6, Hill routes heater/brakes, 50km origin, Orion age/refrigeration, Apex rotation, Guddu jugaad 7-day, Driver night solo, Service overdue grounding, Monsoon east-of-Lucknow).
* `tests/test_pii_security.py`: Validates zero raw PII across all outbox files and query responses.
* `tests/test_entity_resolution.py`: Validates registration normalization, client alias parsing, and conflict hierarchy (`RJ43DD3546` year resolution, `CH67HY8613` odometer maintenance).
* `tests/test_surprise_file.py`: Validates dynamic schema adaptation on mutated ticket files.
* `tests/test_llm_adapter.py`: Validates isolated Gemini perception layer (deterministic-first strategy, no-API-key fallback, PII boundary, invalid JSON handling, API timeout fallback, entity resolution safety).

---

## 6. Project Code Structure

```
c:\Users\MUKUL\Documents\Synq Hackathon\
├── candidate_bundle/            # Original client datasets (untouched)
├── src/
│   ├── config.py                # Hub coordinates, NCR corridors, constants, paths
│   ├── models.py                # Canonical dataclasses (driver_id only, zero names)
│   ├── pii_scrubber.py          # Zero-PII masking gateway & pre-write validator
│   ├── normalizer.py            # Reg plate, client alias, date normalizer
│   ├── context_store.py         # SQLite entity store & conflict resolver
│   ├── rule_engine.py           # Dispatcher expert rules & corridor geometry
│   ├── allocator.py             # Allowed-hub resolution + 4-tier ranking & Why-Not matrix
│   ├── adapter.py               # Dynamic schema adapter for surprise files
│   ├── pipeline.py              # State machine / processing pipeline orchestrator
│   └── comms_gate.py            # Human approval CLI & state tracker
├── outputs/                     # Target Standard Outputs
│   ├── work_orders.jsonl
│   ├── comms_pending.jsonl
│   ├── comms_sent.jsonl
│   └── quarantine.jsonl
├── audit/
│   └── audit.jsonl              # Complete step-by-step decision log
├── tests/                       # Automated PyTest Suite (15/15 passing)
├── run_pipeline.py              # ONE-COMMAND MASTER ENTRYPOINT
├── query_context.py             # Grounded QA CLI with citations
├── inspect_ticket.py            # Evaluator 30-second ticket inspector
└── README.md                    # System documentation
```
