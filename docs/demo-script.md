# Demo video script — Genesis OS: Operational Intelligence (Grafana track)

**Target ≤ 3:00.** Record the HOSTED console (genesis-grafana-console-…run.app) — the
whole loop is cloud-to-cloud: Cloud Run API → official Grafana MCP sidecar → Grafana Cloud →
hosted render farm. Every beat is live-verified.

**Setup (before recording):** trigger the degradation on the hosted farm
(`POST /scenario/degrade` on the render-sim service), wait ~2 min so the incident is mature.

| Time | On screen | Say |
|---|---|---|
| 0:00–0:15 | Incident console masthead; Grafana Cloud dashboard in a second tab showing GPU/queue/latency climbing. | "A film studio's render farm is drowning — GPU saturation, queue backing up. This is Operational Intelligence, built for the Grafana track: an agent hierarchy that reads telemetry the same way you would — through Grafana." |
| 0:15–0:40 | Ask: **"How is production doing right now?"** Investigation launches; stage chips advance OBSERVE→CORRELATE. | "The Executive opens an investigation. Its analysts pull metrics and logs at runtime through the official Grafana MCP server — sixty-plus tools, and every number on this screen came through it. Nothing is invented." |
| 0:40–1:10 | Correlation + diagnosis card: competing hypotheses, supporting AND contradicting signals, confidence ~0.9+, CUDA-OOM root cause. | "It doesn't stop at 'things look bad.' It forms competing hypotheses, weighs evidence for and against each, and lands on a diagnosis: worker pool saturation, CUDA out-of-memory, with the signals to prove it." |
| 1:10–1:30 | Prediction panel: breach ETA on queue capacity. | "Then it looks forward — at this trajectory, the queue breaches capacity in minutes, not hours." |
| 1:30–1:55 | Recommendation card: reduce concurrency; APPROVE waiting. *(Optional 5 s insert: kill the worker in a terminal, then click APPROVE anyway.)* | "The fix is proposed, never self-executed. The approval is a durable Temporal signal — we've killed the worker mid-approval and the decision survived a dead process. Authority is engineered, not promised." |
| 1:55–2:25 | Click **APPROVE**. ACT stage: farm concurrency drops (render-sim control call); VERIFY stage running. | "Approved. The system actuates the real hosted farm — and here's the part that matters: it goes back to Grafana to check its own work." |
| 2:25–2:50 | Verification before/after: GPU, queue, latency down; **REMEDIATED**. Grafana Cloud tab confirms the drop. | "Before and after, from Grafana Cloud itself. Action isn't outcome — verification is. Remediated." |
| 2:50–3:00 | Repo README runtime-proof links; stack line (Temporal·PG·NATS·Redis·Tempo·DataHub). | "Observe, correlate, diagnose, predict, recommend, authorize, act, verify — Genesis OS: Operational Intelligence." |

**Recording notes**
- `site=cloudrun` scoping means the local farm can stay off; the hosted loop is self-contained.
- If the incident resolves before recording, re-trigger degrade and wait for OBSERVING → anomalous.
