# ADR 0001 — Builder implementation choices (Step 2 MVP)

Status: accepted · 2026-08-12

Implements the locked Architecture Review V2 (docs/architecture/). Implementation-level choices only.

1. **Grafana MCP via the MCP Python SDK** (streamable-HTTP): agents call the official server's
   tools at runtime — `list_datasources`, `query_prometheus`, `query_loki_logs`,
   `list_alert_groups`. Verified live against `mcp/grafana` (65 tools): relative time args
   (`now-30m`) are required (the server rejects fractional-second RFC3339), results arrive as
   `{"data": [{"values": [[ts, "v"], …]}]}` / `{"data": [{"line": …}]}`, and streamable-HTTP mode
   needs `-address 0.0.0.0` + `-allowed-hosts` for the published port. Grafana Cloud swap =
   `GRAFANA_MCP_URL` + token, no code change.
2. **Statuses and statistics are computed in code** (anomaly thresholds, slopes, time-to-capacity,
   before/after verification); Gemini reasons over computed facts and never invents telemetry
   (locked §14). Verification decides REMEDIATED vs REMEDIATION_FAILED from re-queried telemetry —
   action submission ≠ outcome (locked §15).
3. **Actuation boundary** = the studio's own control plane (render-farm simulator
   `/control/concurrency`). Reducing concurrency genuinely drains the simulated queue, so live
   verification shows real improvement. `TIME_SCALE` env accelerates the scenario for demos.
4. **Mock mode** mirrors the live scenario deterministically (same agent code paths) so a clean
   clone demonstrates the full loop offline; `GENESIS_MOCK=1` forces it.
5. **Trace Analyst reports honestly** that no tracing datasource is configured (locked failure
   philosophy) — Tempo is the next telemetry increment, not fabricated coverage. Grafana-managed
   alert rules likewise arrive via MCP when provisioned; the local stack currently detects the
   incident from metrics/logs.
6. **google-genai directly** for cognition (accepted SDK, live-callable); no non-Google agent
   frameworks at runtime per hackathon rules.
