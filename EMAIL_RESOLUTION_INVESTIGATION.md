# EMAIL → TICKET RESOLUTION INVESTIGATION

## 1. EMAIL → TICKET TRACE

### Example 1: `thread_25_internal_jugaad.txt`
```text
EMAIL (Internal Workshop Email)
↓
What facts are extracted? None. The email is skipped during parsing because it doesn't contain "apex" and standard vehicle plate formats.
↓
What identifiers exist? Contextual phrase: "kal raat wali gaadi". Mention of "Guddu" and "jugaad".
↓
What identifiers do NOT exist? Canonical vehicle registration, Ticket ID, Client, Driver.
↓
How does current code attempt to associate it? It does not.
↓
Which function performs the association? `_load_incident_history` in `src/context_store.py` (which ignores this file).
↓
What ticket/entity does it resolve to? NOT RESOLVED BY CURRENT IMPLEMENTATION
↓
What evidence supports the association? N/A
```

### Example 2: `thread_01_shakti_sla.txt`
```text
EMAIL (Shakti Cement SLA Reminder)
↓
What facts are extracted? None. It doesn't match the `apex` filter in `_load_incident_history`.
↓
What identifiers exist? Date (Mon, 27 Jul 2026), Client ("Shakti Cement").
↓
What identifiers do NOT exist? Ticket ID, Vehicle Registration.
↓
How does current code attempt to associate it? It does not.
↓
Which function performs the association? `_load_incident_history` in `src/context_store.py` (which ignores this file).
↓
What ticket/entity does it resolve to? NOT RESOLVED BY CURRENT IMPLEMENTATION
↓
What evidence supports the association? N/A
```

### Example 3: `thread_09_vertex_gate.txt`
```text
EMAIL (Vertex Retail gate turn back)
↓
What facts are extracted? None. It doesn't match the `apex` filter in `_load_incident_history`.
↓
What identifiers exist? Vehicle (UP29HF3900), Client (Vertex Retail), Date (24 Jun 2026).
↓
What identifiers do NOT exist? Ticket ID.
↓
How does current code attempt to associate it? It does not.
↓
Which function performs the association? `_load_incident_history` in `src/context_store.py` (which ignores this file).
↓
What ticket/entity does it resolve to? NOT RESOLVED BY CURRENT IMPLEMENTATION
↓
What evidence supports the association? N/A
```

---

## 2. CRITICAL EXAMPLE: "KAL RAAT WALI GAADI"
**File**: `thread_25_internal_jugaad.txt`

1. **What vehicle is explicitly mentioned?** None.
2. **Is a canonical vehicle registration present?** No.
3. **Is the phrase "kal raat wali gaadi" used?** Yes.
4. **Does the email contain a date?** Yes, in the header (`Tue, 11 Aug 2026`).
5. **Does it contain a client?** No.
6. **Does it contain a ticket ID?** No.
7. **How does current code identify the vehicle?** It doesn't.
8. **exact code path:** N/A. `_load_incident_history` in `context_store.py` checks `if "apex" in content_lower` (line 248). Because "apex" is not in this email, the file is entirely ignored.
9. **If it does not, say so.** It does not identify the vehicle.

---

## 3. MULTI-SOURCE GRAPH FOR ONE TICKET (TKT-0027)

```text
TKT-0027
│
├── Ticket record (Source: `tickets.json`, exact match on `ticket_id`)
│
├── Vehicle (Source: `tickets.json` -> `context_store.py::get_vehicle()`. Normalized exact matching to `fleet_master.csv`)
│
├── Driver (Source: `tickets.json` -> `context_store.py::get_driver()`. Exact match on `driver_id` to `drivers_roster.csv`)
│
├── Client (Source: `tickets.json` -> `CLIENT_METADATA` in `config.py`. Exact matching)
│
├── Maintenance (Source: `tickets.json` vehicle -> `context_store.py::has_recent_brake_work()`. Normalized vehicle matching against `maintenance_log.xlsx` via temporal rules)
│
├── Email(s)
│   NOT CURRENTLY CONNECTED
│
├── Dispatcher knowledge (Source: Hardcoded in `src/rule_engine.py` functions like `evaluate_driver_safety`. Triggered via exact/conditional property matching like checking BS Stage or winter months.)
│
└── Contract/SLA (Source: Hardcoded in `CLIENT_METADATA` dictionary based on client name)
```

---

## 4. DISTINGUISH CONTEXT LOADING FROM RELEVANCE RETRIEVAL

The current system uses **Approach A: Loads (a limited subset of) available facts into a database and later queries by entity**. 

It **DOES NOT** dynamically determine which documents are relevant to each ticket.

**Real Code Explanation:**
In `src/context_store.py` during initialization, the system runs `_load_incident_history()`. This function loops over every `.txt` file in `emails/`. If the email contains the word "apex" and words like "incident" or "broke down", it extracts any string that looks like a license plate via regex (`r'[A-Z]{2}[-\s]?[0-9]{1,2}...`) and inserts it into a SQLite table `client_incident_history`. 
Later, the rule engine queries the SQLite table (e.g. `get_last_apex_incident_vehicle()`).

At no point does the `pipeline.py` take `TKT-0027` and "search" for relevant emails. The emails are parsed globally at startup, and only highly specific explicit patterns are saved.

---

## 5. SEARCH MECHANISM AUDIT

| Mechanism | Exists? | File | Function | Used For |
| --------- | ------- | ---- | -------- | -------- |
| ticket ID matching | Yes | `pipeline.py` | `process_ticket_queue` | Deduplication (`seen_ticket_ids`) |
| vehicle ID matching | Yes | `context_store.py` | `get_vehicle` | Fleet lookups |
| normalized vehicle registration | Yes | `normalizer.py` | `normalize_vehicle_reg` | Scrubbing user inputs before lookup |
| client matching | Yes | `pipeline.py` | `process_ticket_queue` | SLA config lookups (`CLIENT_METADATA`) |
| driver matching | Yes | `context_store.py` | `get_driver` | Retrieving driver info |
| date matching | Yes | `rule_engine.py` | `evaluate_brakes` | Checking if brake maintenance < 30 days |
| timestamp proximity | No | N/A | N/A | N/A |
| route matching | No | N/A | N/A | N/A |
| keyword matching | Yes | `context_store.py` | `_load_incident_history` | Hardcoded `if "apex" in content_lower` |
| filename matching | No | N/A | N/A | N/A |
| regex | Yes | `context_store.py` | `_load_incident_history` | Extracting license plates from text |
| fuzzy matching | No | N/A | N/A | N/A |
| SQLite query | Yes | `context_store.py` | `get_last_apex_incident_vehicle` | Retrieving past incident state |
| full-text search | No | N/A | N/A | N/A |
| embeddings | No | N/A | N/A | N/A |
| vector database | No | N/A | N/A | N/A |
| semantic search | No | N/A | N/A | N/A |
| Gemini | Yes | `llm_adapter.py` | `extract_unstructured_facts` | Mapping JSON schema differences |
| graph structure | No | N/A | N/A | N/A |

---

## 6. HINGLISH CAPABILITY AUDIT
Using `thread_25_internal_jugaad.txt`:

### Deterministic parser
Can it understand the operational meaning? **NO**
*(Regex ignores it entirely because it doesn't match standard patterns)*

### Gemini fallback
Can Gemini extract the operational facts? **NOT TESTED**
*(The `GeminiPerception` class could extract the meaning, but the `pipeline` currently never feeds this email to the LLM adapter).*

### Entity resolution
Can the extracted fact be connected to a canonical vehicle/entity? **NO**
*(The phrase "kal raat wali gaadi" requires temporal graph querying of what vehicles arrived last night, which the system does not do).*

### Rule engine
Can the resulting fact trigger the correct deterministic rule? **NO**
*(The rule engine cannot act because the context store doesn't load the jugaad fact).*

---

## 7. IMPLICIT REFERENCE CHALLENGE SET

| Example | Explicit ID? | Entity Explicit? | Context Required? | Current System Resolves? | LLM Potentially Useful? |
| ------- | ------------ | ---------------- | ----------------- | ------------------------ | ----------------------- |
| `thread_25_internal_jugaad.txt` | No | No ("kal raat wali gaadi") | Yes (What vehicle broke last night?) | No | Yes (Language translation) |
| `thread_09_vertex_gate.txt` | No | Yes (UP29HF3900) | No | No | No (Deterministic regex works) |
| `thread_01_shakti_sla.txt` | No | No ("Jaipur loads") | Yes (Which trucks went to Jaipur?) | No | Yes (Intent extraction) |
| `thread_13_apex_rotation.txt` | No | Yes (UP15CQ4127) | No | Yes (Hardcoded regex finds it) | No (Deterministic regex works) |
| `thread_22_internal_odoconflict.txt` | No | No ("that old Tata we sent to Pune") | Yes (Fleet matching by Make/Dest) | No | Yes (Entity extraction) |

---

## 8. WHAT GEMINI CURRENTLY DOES

Gemini currently performs: **A. fact extraction only**

**Exact Code (`src/llm_adapter.py`):**
```python
def extract_unstructured_facts(self, text: str) -> PerceptionFacts:
    # Extracts basic fields (client, driver_id, vehicle_reg, incident_date) into a Pydantic model
    prompt = f"Extract facts to JSON: {text}"
    # ...
    response = self.client.models.generate_content(...)
    return PerceptionFacts(**parsed)
```
It does not search for documents. It does not resolve entities (resolution happens post-LLM extraction in `pipeline.py`).

---

## 9. WHAT IS CURRENTLY MISSING?

### Can the current system take `TKT-0027` and automatically discover every semantically relevant email about that incident?
**NO.** The system does not link emails to specific tickets at runtime.

### Can the current system resolve `"kal raat wali gaadi"` to a canonical vehicle?
**NO.**

### Can it resolve Hinglish operational meaning?
**NO.**

### Can it connect an implicitly referenced incident to a ticket?
**NO.**

---

## 10. VECTOR STORE DECISION — ANALYSIS ONLY

| Problem | Vector Store Helps? | Why? | Better Alternative? |
| ------- | ------------------- | ---- | ------------------- |
| **Document Retrieval** | **Yes** | Can retrieve similar emails based on keywords like "broken down" or "jugaad". | None, vector search is good for unstructured text retrieval. |
| **Entity Resolution** | **No** | It returns text documents, but does not execute logic (e.g., figuring out which truck went to Kanpur last night). | Knowledge Graph / SQL Temporal Joins + LLM. |
| **Language Understanding** | **No** | Vector matching might group Hinglish texts, but it won't translate or parse operational facts from them. | Direct LLM extraction (like Gemini) before storing. |
| **Business Decision** | **No** | Cannot enforce the "7-day jugaad" rule deterministically. | Deterministic Python Rule Engine (current architecture). |

---

## 11. FINAL ARCHITECTURAL FINDING

* **What works today:** The deterministic rule engine, schema adapter, and exact-match entity lookups (e.g., matching a ticket driver ID to the roster).
* **What works only for explicit identifiers:** Email parsing. Only exact license plate regexes trigger anything.
* **What works for normalized identifiers:** The pipeline correctly normalizes raw JSON plates before hitting the database.
* **What works for unstructured language:** Nothing in the emails. The Gemini adapter is currently only used on the *ticket* input if the ticket schema is malformed.
* **What works for Hinglish:** Nothing.
* **What does NOT currently work:** Any implicit reference ("kal raat wali gaadi"), mapping arbitrary emails to tickets, understanding complex Hinglish constraints from emails.
* **Whether the current system is actually doing multi-source ticket resolution:** No. It is processing tickets deterministically against statically loaded master data, with a hardcoded hack for Apex rotation.
* **Whether vector search is needed for the current challenge:** No. A vector search will just return a Hinglish email. The system still wouldn't know *which* vehicle it refers to, nor what rule to apply.
* **What the smallest architectural improvement would be, IF one is actually necessary:** Run all emails through Gemini *at ingestion time* to extract structured metadata (Vehicle, Date, Constraint). If the vehicle is implicit ("kal raat wali gaadi"), query the trip database (using an LLM tool or deterministic lookup) to resolve the canonical vehicle. Store the result in `ContextStore`.
