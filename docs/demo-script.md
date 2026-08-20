# Demo video — Genesis OS: Operational Intelligence (Grafana track)
## Format: the highlight reel of a streamer whose game is protecting a render farm

**The frame:** inside the code the agent is a legend — live on its own board,
making plays, saving clips. Outside the code it is a program a studio head
trusts to keep the studio's render farm healthy. The video plays both notes:
caster commentary over the reel, and one pull-back at the end.

**Why this format wins the clock:** capture and narration are decoupled. Part
A gathers footage with no time pressure (the clips library replays on
demand); Part B is a 3:00 narration recorded over the edit. No live-demo
timing risk. Every frame shows recorded reality — replays are labelled as
replays, records only exist where a faster fix actually happened, and the
track brief's checklist stays visibly intact: firing alert → MCP retrievals
→ logs-with-traces correlation → root cause → human approval → dashboard
annotations → verification, plus the mirror.

---

## Part A — the capture session (no clock)

Prep once:
1. `POST :9105/scenario/auto/off` (clean verification windows) ·
   `POST :9105/scenario/clear` · let the farm settle ~1 min.
2. Clear stale runs in the console history; confirm the latch is free.
3. Tabs: the console (:3010) · The Slate + Farm Floor + The Agent (Grafana
   Cloud) · one terminal for scenario POSTs (off-camera).

Collect these takes (order matters — the memory arc needs repeats):
- **Save #1 — VRAM:** `POST :9105/scenario/gpu_oom`. Wait: queue climbs,
  alert fires, the watcher opens the investigation (~45 s; nobody touches
  anything). Record: the plate (LIVE), the mission banner appearing on its
  own, the split mind filling (cognition left, perception right), the
  approval, verification going green, **🎬 Play saved** and the card landing
  on the shelf. `scenario/clear`, let it settle.
- **Save #2 — a different family** (licence or storage): same flow. NOTE:
  concurrency doesn't fix these two — expect the honest-failure branch OR
  drive `driver`/`gpu_oom` again if this take must win. An honest failure is
  usable footage (the alternate beat below).
- **Save #3 — VRAM again (the learning beat):** `gpu_oom` once more. Record
  the **RECALL line** in the thinking stream and the 🧭 annotation, the
  prior-informed recommendation, the faster clocks, and the **(from memory)**
  clip with its 🧭 badge — plus 🏆 if a record falls.
- **B-roll:** the shelf full of cards; two replays played end-to-end;
  the scoreboard strip + bestiary; The Slate's annotation marks stacking up;
  the risk chart diving after an approval; The Agent dashboard live while
  the loop runs (the mirror); the runtime-proof footer.
- Afterwards: `POST :9105/scenario/auto/on` — give the world its weather back.

---

## Part B — the 3:00 narration (caster voice, recorded over the edit)

| Beat | Footage | Say |
|---|---|---|
| 0:00–0:15 | The board: plate LIVE, slate of five shows, farm floor breathing. | "This is a streamer. The game is protecting a movie studio's render farm — five films, real deadlines. And Grafana is what makes him good at it." |
| 0:15–0:35 | Health band: queue strip crossing its threshold; The Slate's risk stat going red; the alert firing. Mission banner appears alone. | "Health drops. Grafana fires. And watch — nobody presses anything. The alert wakes him. There is no run button on this board, and that's the point." |
| 0:35–1:05 | The split mind: commentary line streaming; cognition ticking left, perception right; a View-in-Grafana jump; a traceID hop from a log line to its Tempo trace. | "Split screen on his mind. Left: what he's thinking — real model calls, tokens and all. Right: what he's seeing — every retrieval through the official Grafana MCP server, sixty-plus tools. The logs name the shots; every line is one click from its trace." |
| 1:05–1:30 | Root cause card; annotation marks landing on The Slate; the approval; ACT/VERIFY; before/after rolls green; **🎬 Play saved**. | "Root cause called — and signed on the dashboard, through MCP. The fix waits for the studio head; approval is a durable signal. Then he checks his own work in Grafana… save confirmed. And he clips it." |
| 1:30–2:00 | **The learning beat:** second VRAM incident — RECALL line, 🧭 annotation, faster clocks, the (from memory) card with 🏆. | "Same fault, days later. But look at the top of his mind: he remembers. Three similar incidents, this fix verified before. Priors inform — evidence decides — and the clock says the rest: he's faster now. That clip goes in the bin with a record badge, because the record actually fell." |
| 2:00–2:20 | The shelf: cards, badges, streak; the scoreboard strip; the bestiary. One replay runs. | "The career is real math — streaks break on failure, times fall only when they fall. Five kinds of faults; faced and beaten. He saves his best plays, and every replay is recorded data — labelled as a replay." |
| 2:20–2:40 | The Agent dashboard while the loop runs: Gemini calls, tokens, cost, MCP tools. | "And the wildest part: Grafana is streaming HIM. Every thought, every token, every tool call — the observer, observed. Build an agent that uses observability data; then observe the agent you build." |
| 2:40–3:00 | **The pull-back:** cut from the reel to the sober board — status chips, runtime proof, the farm green, five shows on schedule. Hold. | "Inside the code, he's a legend. Outside… it's just a program a studio head trusts to keep the render farm healthy. Genesis OS: Operational Intelligence. You just watched the reel." |

**Alternate beat (if an honest failure was captured):** insert at ~2:00 —
"and when a fix doesn't hold, he says so — on the record, on the dashboard.
Action submitted is not outcome achieved. That's why the streak means
something."

**Recording notes**
- One investigation at a time (the latch); the plate's numbers update ~10 s.
- Free Grafana Cloud stacks hibernate — warm the tabs before capturing.
- The replay player is itself demo footage: it runs unattended once opened.
