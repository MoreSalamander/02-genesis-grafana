# Agent Contracts — Operational Intelligence

All cognition flows through the role-based `Cognition.generate_json(role, payload)` interface
(identical in LIVE Gemini and MOCK modes); all telemetry flows through the Grafana MCP interface
(`query_metric` / `query_logs` / `list_alerts`), live or mock.

| Agent | Consumes | Produces | Permissions (§16) |
|---|---|---|---|
| Operational Executive | Studio Head question | Investigation lifecycle, ACT/VERIFY execution | read, analyze, recommend, execute:approval-only |
| Metrics / Log / Trace Analysts + Alert Scanner | Grafana MCP tools | `TelemetryEvidence[]` with computed stats + anomaly flags | read, analyze |
| Correlation Agent | evidence signals | `CausalHypothesis` (validated against anomaly coverage) | read, analyze, recommend |
| Incident Diagnosis Agent | signals + log summary | competing `DiagnosisHypothesis[]` (supporting AND contradicting evidence) | read, analyze, recommend |
| Risk / Prediction Agent | queue series + capacity | `RiskProjection` (eta computed in code from real slopes) | read, analyze, recommend |
| Remediation Planning Agent | leading diagnosis | `RemediationPlan` (authorization always required) | read, analyze, recommend, execute:restricted |
| Studio Head (human) | incident card + evidence | decision: approved / rejected | authorize |

## Operational Intelligence Contract (federation boundary)

The standalone HTTP API doubles as the contract surface Genesis OS will adapt to later:

- `POST /api/investigations {question}` → investigation id
- `GET /api/investigations/{id}` → evidence, hypotheses, projection, plan, verification (operational evidence)
- `POST /api/investigations/{id}/decision {approved|rejected}` → act + verify (bounded execution)
- `GET /api/events` → operational event stream (`anomaly.detected`, `diagnosis.formed`, `remediation.verified`, …)

Genesis OS consumes this contract through an adapter; this system never calls Genesis OS.
