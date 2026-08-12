# Genesis OS — Operational Intelligence

**Agentic operational cognition for an AI-native film studio.** Ask "How is production doing right now?" and watch an agent hierarchy investigate through the **Grafana MCP server** — querying metrics, logs, and alert rules at runtime — then correlate signals into a causal hypothesis, weigh **competing** root-cause diagnoses, project what breaks next, and put a bounded remediation in front of the human **Studio Head**. On approval it acts on the studio's control plane and **verifies the outcome through Grafana** — because action submission is never outcome.

> **Genesis OS Suite** — this is System 02 of Genesis OS, an operating environment for the fictional
> **Convergence Studios**. Each system is a fully standalone submission:
> 01 Signal Intelligence (Parallel) · **[02 Operational Intelligence (Grafana)]** · 03 Institutional
> Intelligence (ClickHouse) · 04 Enterprise Decision Intelligence (IBM + Bob) · 05 Autonomous Studio
> Construction (Replit) — federated later by Genesis OS, never dependent on it.

*Google Cloud Agentic Cinema Hackathon — Grafana track.*

## The locked operational loop

```
OBSERVE → CORRELATE → DIAGNOSE → PREDICT → RECOMMEND → AUTHORIZE → ACT → VERIFY
   │           │           │          │          │           │        │       │
Grafana MCP  hypothesis  competing  time-to-  bounded    Studio   studio   Grafana MCP
(metrics,    validated   root-cause threshold remediation  Head   control  re-queried:
logs,        against     hypotheses (computed  plan       decides  plane   before/after
alerts)      evidence    w/ contra-  from real                             must improve
                         dictions    slopes)
```

Agent hierarchy (locked): **Operational Executive** → Metrics / Log / Trace Analysts + Alert Scanner → Correlation Agent → Incident Diagnosis Agent → Risk/Prediction Agent → Remediation Planning Agent — each with scoped permissions (read → analyze → recommend → execute-restricted).

Full locked architecture: [docs/architecture/system-02-grafana.v2.locked.md](docs/architecture/system-02-grafana.v2.locked.md)

## Runtime integrations (the ones that matter)

| Requirement | Where it lives |
|---|---|
| **Grafana stack at runtime via the official Grafana MCP server** (`query_prometheus`, `query_loki_logs`, `list_alert_rules`, `list_datasources` over streamable-HTTP) | [`app/tools/grafana/mcp_client.py`](app/tools/grafana/mcp_client.py) |
| **Gemini at runtime** (official `google-genai` SDK) | [`app/tools/google/gemini.py`](app/tools/google/gemini.py) |
| Closed-loop actuation + verification | [`app/agents/executive/executive.py`](app/agents/executive/executive.py) |
| Human authority boundary & permission tiers | [`app/governance/authority.py`](app/governance/authority.py) |

## Quickstart

```bash
# 1. Install (Python 3.11+)
uv venv .venv && uv pip install -p .venv -e ".[dev]"

# 2. Run — with no config this boots in MOCK mode (deterministic render-pipeline
#    incident, full OBSERVE→…→VERIFY loop demonstrable offline)
.venv/bin/uvicorn app.main:app --port 8010
# open http://localhost:8010  (API docs at /docs)

# 3. Go LIVE with the local Grafana stack (Grafana + Prometheus + Loki +
#    official mcp/grafana server + render-farm simulator):
cd ops && docker compose up -d && cd ..
cp .env.example .env   # set GRAFANA_MCP_URL=http://localhost:8686/mcp
#                        (+ GOOGLE_API_KEY for live Gemini cognition)
# Grafana UI: http://localhost:3001 (admin/genesis) — "Studio Operations" dashboard
# Grafana Cloud instead: point GRAFANA_MCP_URL at your stack's hosted MCP endpoint + token.
```

Run an investigation:

```bash
curl -s -X POST localhost:8010/api/investigations \
  -H 'content-type: application/json' \
  -d '{"question": "How is production doing right now?"}'
# poll:    curl -s localhost:8010/api/investigations | python3 -m json.tool
# approve: curl -s -X POST localhost:8010/api/investigations/<id>/decision \
#            -H 'content-type: application/json' -d '{"decision":"approved"}'
```

## Tests

```bash
.venv/bin/pytest -q
```

Covers the full loop to the authorization gate, approve→act→verify with genuine before/after improvement, rejection (nothing executes), **failed verification → escalation** (action submission ≠ outcome), decision guards, and that risk projections use real computed slopes.

## License

MIT — see [LICENSE](LICENSE).
