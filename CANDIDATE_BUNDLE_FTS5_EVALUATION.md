# FTS5 Real Data Evaluation

| Case | Query/Ticket Context | Expected Evidence | Found? | Rank | Candidates | Cross-Client Rejected? | Notes |
|------|----------------------|-------------------|--------|------|------------|------------------------|-------|
| Contextual Reference ('Kal raat wali gaadi') | Client: Internal<br>Vehicle: <br>Issue: engine check needed | thread_25_internal_jugaad.txt | No | - | 9 | N/A | Testing if FTS5 can bridge 'kal raat wali gaadi' without exact vehicle ID. |
| Vertex Retail SLA exception | Client: Vertex Retail<br>Vehicle: <br>Issue: delay in transit | thread_09_vertex_gate.txt | Yes | 1 | 2 | N/A | Testing retrieval of SLA rules based on client name. |
| Apex Chemicals Incident Rotation | Client: Apex Chemicals<br>Vehicle: UP14BT8899<br>Issue: breakdown enroute | thread_13_apex_rotation.txt | Yes | 2 | 3 | N/A | Testing exact vehicle/client match. |
| Maintenance Jugaad Check | Client: UNKNOWN<br>Vehicle: CH67HY8613<br>Issue: brake overheating | maintenance_log.xlsx | Yes | 2 | 10 | N/A | Testing if maintenance notes are retrieved for vehicle. |
| Cross Client Rejection (Shakti) | Client: Shakti Cement<br>Vehicle: <br>Issue: plant delivery | thread_01_shakti_sla.txt | Yes | 1 | 5 | Yes | Testing if Apex/Vertex emails are successfully rejected. |
