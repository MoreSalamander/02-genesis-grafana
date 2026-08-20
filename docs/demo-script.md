# Demo video script — Genesis OS: Operational Intelligence (Grafana track)

**Target ≤ 3:00.** The arc is the track brief's own sentence, verbatim:
*investigate a firing alert → correlate Loki logs with Tempo traces → summarize
root cause → annotate a dashboard* — plus its thesis, *observe the agent you
build*. Every beat below is live-verified; nothing is narrated over a mock.

**Setup (before recording):**
1. `POST :9105/scenario/auto/off` — a clean verification window (background
   incidents would honestly sabotage the recovery beat, which is a feature,
   but not the one this take is about).
2. `POST :9105/scenario/clear`, let the farm settle ~1 min.
3. `POST :9105/scenario/gpu_oom` — the incident concurrency genuinely fixes.
4. Wait ~2–3 min: queue climbs past 120, **Render queue overflow risk** fires;
   Aurora Falls' delivery-risk follows it red on The Slate.
5. Tabs ready: The Slate (Grafana Cloud) · Farm Floor · the 02 console ·
   The Agent dashboard.

| Time | On screen | Say |
|---|---|---|
| 0:00–0:18 | **The Slate** dashboard: five shows, Aurora Falls' risk stat flipping red — "projected late". The alert list starts firing. | "Convergence Studios renders five films on this farm. Aurora Falls delivers Friday — and right now, Grafana is watching her projection slip past the date. An alert fires. Nobody typed a question." |
| 0:18–0:40 | Cut to the 02 console: a new investigation appears **on its own**, wearing the red banner — ⚡ OPENED BY A FIRING ALERT. Stage chips advance. | "The agent noticed. It reads the alertmanager through the official Grafana MCP server — sixty-plus tools — and opened this investigation itself. The alert rides on the record: this run exists because Grafana said so." |
| 0:40–1:10 | Evidence grid fills; click **View in Grafana ↗** on the queue signal — lands on the exact panel, exact window. Back to console: log lines with `show=aurora-falls`. | "Every signal it gathers links back to the panel it lives on — evidence you can audit. The logs name the shots; each line carries a trace ID, and in Grafana that's one click from a log line to the exact Tempo trace of the frame that suffered." |
| 1:10–1:30 | Farm Floor: state timeline lanes going red; duration heatmap band shifted. Diagnosis card in console: CUDA-OOM, confidence, competing hypotheses. | "Logs correlated with traces, hypotheses weighed for and against: heavy scenes are blowing VRAM — CUDA out of memory. And this isn't 'the farm is slow.' It's 'Aurora Falls pays for this.'" |
| 1:30–1:50 | The Slate dashboard: purple annotation marks appear — 🔎 opened, 🧠 root cause. Hover one. | "The agent signs its work where operators actually live: annotations on the dashboards, written through MCP. Investigation opened. Root cause found. On the record, on the graphs." |
| 1:50–2:15 | Console: recommendation card. Click **✓ Approve remediation**. ACT → VERIFY chips. Annotation trail chips grow: decision-approved, remediation-applied. | "The fix is proposed, never self-executed — my approval is a durable Temporal signal. The moment I decide, that decision is annotated onto Grafana too, with the whole audit trail." |
| 2:15–2:40 | Verification panel: before/after grid goes green, REMEDIATED seal. The Slate: Aurora's risk stat falls back below zero. ✅ recovery annotation lands. | "It goes back to Grafana to check its own work. Queue draining, latency down — and the number that matters: Aurora Falls' projection back inside her delivery date. The deadline, bought back." |
| 2:40–2:55 | **The Agent** dashboard: Gemini calls with tokens and cost, MCP tool calls by name, live during everything we just watched. | "And the whole time, Grafana was watching the agent itself — every Gemini call, every token, every MCP tool it used. Build an agent that uses observability data. Then observe the agent you build." |
| 2:55–3:00 | The Slate, zoomed to the annotation trail: five purple marks telling the whole story. | "Genesis OS: Operational Intelligence. The story is on the dashboard." |

**Recording notes**
- The loop is autonomous: if the alert is firing, the investigation opens
  within ~45 s (`ALERT_WATCH_INTERVAL_S`). Don't type a question on camera.
- One investigation at a time (the latch): clear stale runs before the take.
- Cloud stacks hibernate on free tier — open the Grafana Cloud tabs a few
  minutes early so everything is warm.
- If verification honestly fails on camera (a background incident stole the
  window), that's the alternate ending: the system refuses to claim success,
  escalates, and says so on the dashboard. It has happened live; it reads as
  integrity. But `auto/off` makes the clean take reliable.
- After recording: `POST :9105/scenario/auto/on` to give the world back its
  weather.
