# CANDIDATE_BUNDLE_FORENSIC_DATA_REPORT

## 1. COMPLETE DATA INVENTORY
The `candidate_bundle/` directory contains 49 files totaling roughly 3MB of raw data. The breakdown is as follows:

**Structured Data:**
* `meridian_trips.csv` (2.67 MB) - Sample of historical trips containing dispatch/delivery times, OSRM distances vs actuals, and billed amounts.
* `maintenance_log.xlsx` (15.8 KB) - 250 rows of maintenance events including date, vehicle, odometer, mechanic, and free-text notes.
* `fleet_master.csv` (7.8 KB) - 118 rows defining the fleet configuration (capacity, BS stage, engine heater status, home hub). 18 rows lack a `vehicle_id`.
* `drivers_roster.csv` (5.3 KB) - 60 rows of driver metadata including IDs, names, PII (phone, Aadhar, DL), and joining dates.
* `tickets.json` (12.7 KB) - 35 structured breakdown incident tickets.

**Unstructured / Semi-structured Data:**
* `emails/` directory (40 `.txt` files) - Internal and client communication threads. 
* `dispatcher_interview.txt` (7.6 KB) - Transcript of an interview with a senior dispatcher containing critical business logic.
* `Synq_AI_FDE_Challenge_Deck.pptx` & `Synq_AI_Forward_Deployment_Challenge.pdf` - Project briefing materials.

## 2. STRUCTURE & SCHEMA MUTATION
The data exhibits significant schema inconsistencies and "messiness" typical of real-world operations:

* **Missing References in Tickets:** Among the 35 tickets, there are intentional gaps. 2 tickets have unknown/missing drivers (e.g., `DRV-999`, `null`), and 2 have unknown/missing vehicles (e.g., `HR??UNKNOWN`, `""`).
* **Format Variations:** Vehicle registration numbers are wildly inconsistent across datasets. In `fleet_master.csv` they appear as `UP17GN7381`. In `maintenance_log.xlsx`, they mutate into formats like `UK79WJ9666`, `DL-64-IB-1058`, and lowercase `ch40ik6238`. 
* **JSON Consistency:** The `tickets.json` keys are uniform across all 35 tickets (e.g., `ticket_id`, `vehicle`, `driver_id`, `issue`), but the values they contain (like the missing IDs) require robust fallback handling.

## 3. PII & COMPLIANCE OBSERVATIONS
* **Rampant PII in Emails:** 100% (40/40) of the email threads contain personally identifiable information (PII) such as phone numbers (e.g., `+91-XXXXX`) or email addresses (`@meridianfreight.example.in`). 
* **Roster Exposure:** `drivers_roster.csv` contains highly sensitive plaintext data including Aadhaar numbers, driver's license numbers, and personal phone numbers.
* **Compliance Risk:** Any direct ingestion of these files into a 3rd-party LLM without a scrubbing layer is a severe compliance violation.

## 4. LANGUAGE & TRIBAL KNOWLEDGE
The dataset is not clean, standardized English.

* **Hinglish Usage:** Operational communications contain Hinglish. For example, `thread_25_internal_jugaad.txt` reads: *"Guddu ne kal raat wali gaadi jugaad se chalu kar di thi. Reminder set kiya hai, permanent repair within 7 days..."* 
* **Tribal Knowledge:** `dispatcher_interview.txt` is the actual source of truth for operations, overriding standard SLAs. It contains "unwritten" rules such as:
  * *Winter Delhi runs:* BS6 vehicles only for NCR routes (Oct-Feb).
  * *Hills:* No brake work in the last 30 days; engine heaters mandatory.
  * *Shakti Cement:* 36-hour internal SLA overrides the 48-hour contract.
  * *Vertex Retail:* No deliveries after 6 PM (held at last halt).
  * *Apex Chemicals:* Vehicle rotation required (no back-to-back runs for problem trucks).
  * *Orion Pharma:* 2020+ vehicles only, no unrefrigerated overnight waits.
  * *Maintenance:* Any truck >30 days overdue is grounded.
  * *Jugaad fixes:* 7-day clock for a permanent repair; vehicle restricted to home region.
  * *Dispatch radius:* Breakdowns within 50km use the origin hub; >50km use the nearest eligible hub.

## 5. IDENTIFIER GRAPH & RESOLUTION
Connecting an email to a ticket is exceptionally difficult due to implicit references.
* **No Explicit Joins:** **0 out of 40** email threads contain an explicit `TKT-XXXX` identifier. 
* **Contextual Entity Resolution:** Emails refer to entities contextually, such as *"kal raat wali gaadi"* (yesterday night's vehicle) or *"Shakti loads"*. 
* **Graph Breakdown:** To map an email to a ticket, the system must infer the relationship based on timestamps (e.g., matching the date of the email to the `created_at` of a ticket) and entities (e.g., mapping the dispatcher's mention of a client/route to a ticket's `client` or `destination` fields).

## 6. RETRIEVAL (RAG) REQUIREMENTS
* **Is this a RAG problem?** No. Standard Retrieval-Augmented Generation (semantic similarity search over vector embeddings) is the wrong architecture for this data. 
* **Why RAG Fails Here:** 
  1. A vector search for "truck broken down" will retrieve 40 similar but unrelated emails, mixing up different clients and vehicles.
  2. The unwritten rules in the dispatcher interview are conditional logic (e.g., "IF route=Delhi AND month=Oct-Feb THEN BS_Stage=6"), which vector DBs cannot reliably enforce.
* **Correct Approach:** This requires a deterministic Knowledge Graph or State Machine that uses exact-match filtering (by date, hub, client) combined with LLMs strictly for extracting structured facts (Entity Extraction) from emails, rather than semantic retrieval.

## 7. CONFLICT ANALYSIS
* **Contract vs. Reality:** Explicit conflicts exist between documented SLAs and operational reality (e.g., Shakti's 48h contract vs 36h reality). 
* **Data Integrity:** `tickets.json` references vehicles that do not exist in the `fleet_master.csv` (e.g. `HR??UNKNOWN`).
* **Maintenance Logs vs Operations:** A vehicle might be "Active" in the fleet master but grounded according to the maintenance log (e.g., due to the 30-day overdue rule or the 7-day 'jugaad' rule).

## 8. QUALITY SCORECARD
| Aspect | Score (1-10) | Notes |
| :--- | :--- | :--- |
| **Schema Uniformity** | 4/10 | High variance in identifier formats (plates, names). |
| **Referential Integrity** | 2/10 | Missing foreign keys; emails completely lack ticket IDs. |
| **PII Safety** | 1/10 | Raw data is highly toxic; direct LLM ingestion is unsafe. |
| **Rule Explicitness** | 3/10 | Core logic is buried in a conversational transcript. |

**Conclusion:** The data proves that the deterministic, hardcoded core we've built is absolutely necessary. LLMs should only be used to normalize the "messy" inputs (like extracting plates from Hinglish emails) so they can be fed into our strict deterministic rule engine.
