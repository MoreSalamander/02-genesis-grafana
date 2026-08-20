"use client";
import { Fragment, useCallback, useEffect, useState } from "react";
import {
  ACTIVE, EventRecord, InvestigationDetail, InvestigationSummary, SystemStatus,
  VerificationResult,
  decideInvestigation, getEvents, getInvestigation, getStatus, listInvestigations,
  clearInvestigation, simulateIncident,
} from "@/lib/api";
import { AnomChip, SeverityChip, StatusChip } from "./components/Chips";
import { Sparkline } from "./components/Sparkline";
import { FarmFloor } from "./components/FarmFloor";
import { SlateBoard } from "./components/SlateBoard";
import { RiskLines, StatTile, Strip, useTelemetryHistory } from "./components/OpsWall";
import { getCognition, getPerception } from "@/lib/api";
import { PlaysShelf } from "./components/Plays";
import { getScoreboard } from "@/lib/api";
import { Section } from "./components/Section";
import {
  Elapsed, Note, Pulse, Rolling, RuntimeBar, Stamp, Stream, VoiceLine,
  cascade, proofItems, proofState, useCursorGlow, voiceFor,
} from "@/lib/alive";

const LOOP = ["OBSERVE", "CORRELATE", "DIAGNOSE", "PREDICT", "RECOMMEND", "AUTHORIZE", "ACT", "VERIFY"];

// Which loop step a live status is standing on — drives the shimmer and the
// elapsed clock, so the console shows motion only where work is real.
// The ops room's own voice. Chips keep the formal state; this says what it is
// doing, in the first person, above them.
const VOICE: Record<string, string> = {
  OBSERVING: "I'm reading the render pipeline — pulling live telemetry through Grafana.",
  CORRELATING: "I'm looking for what moved together, and in what order.",
  DIAGNOSING: "I'm weighing competing explanations against the evidence.",
  PREDICTING: "I'm projecting what breaks next if nothing changes.",
  AWAITING_AUTHORIZATION: "I have a remediation ready. I need your decision.",
  ACTING: "Applying the remediation now.",
  VERIFYING: "Checking whether it actually worked — same metrics, measured again.",
  REMEDIATED: "Remediated. The telemetry agrees with the fix.",
  REMEDIATION_FAILED: "The fix didn't hold. Action submitted is not the same as outcome achieved.",
  REJECTED: "Understood — remediation declined.",
  ESCALATED: "The diagnoses are too close to call. This needs a human.",
  INCOMPLETE: "I couldn't observe enough to answer honestly. Nothing was inferred.",
  HEALTHY: "I looked, and found nothing wrong.",
};

const STATUS_STEP: Record<string, string> = {
  OBSERVING: "OBSERVE",
  CORRELATING: "CORRELATE",
  DIAGNOSING: "DIAGNOSE",
  PREDICTING: "PREDICT",
  AWAITING_AUTHORIZATION: "AUTHORIZE",
  ACTING: "ACT",
  VERIFYING: "VERIFY",
};

export default function CommandConsole() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [items, setItems] = useState<InvestigationSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<InvestigationDetail | null>(null);
  const [events, setEvents] = useState<EventRecord[]>([]);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const [career, setCareer] = useState<import("@/lib/api").Scoreboard | null>(null);
  useCursorGlow();

  useEffect(() => {
    let alive = true;
    const load = () => getScoreboard().then((b) => alive && setCareer(b)).catch(() => {});
    load();
    const t = setInterval(load, 10000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  const refresh = useCallback(async () => {
    try {
      const [st, list] = await Promise.all([getStatus(), listInvestigations()]);
      setStatus(st);
      setItems(list);
      if (selected) {
        const [d, ev] = await Promise.all([getInvestigation(selected), getEvents(300)]);
        setDetail(d);
        setEvents(ev.filter((e) => e.investigation_id === selected));
      }
    } catch { /* backend may be restarting */ }
  }, [selected]);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 1500);
    return () => clearInterval(t);
  }, [refresh]);

  const decide = async (decision: "approved" | "rejected") => {
    if (!detail || busy) return;
    setBusy(true);
    setNote("");
    try {
      await decideInvestigation(detail.id, decision);
      setNote(`Decision "${decision}" accepted — remediation ${decision === "approved" ? "executing" : "declined"}.`);
      await refresh();
    } catch (err) {
      setNote(`Decision failed: ${String(err).slice(0, 200)}`);
    } finally { setBusy(false); }
  };

  // Ending a run is a real action, not just hiding a row: a run still mid-loop
  // is stopped and removed, and the audit trail records that it was cleared.
  const clear = async (id: string) => {
    try {
      const res = await clearInvestigation(id);
      if (selected === id) { setSelected(null); setDetail(null); }
      setNote(res.was_running
        ? `Ended and cleared a run that was still ${res.was.toLowerCase()}.`
        : "Investigation cleared.");
      await refresh();
    } catch (err) {
      setNote(`Could not clear that investigation: ${String(err).slice(0, 160)}`);
    }
  };

  const triggerIncident = async () => {
    try { await simulateIncident(); setNote("Incident injected into the render farm — telemetry is degrading."); }
    catch { setNote("Simulator not reachable (live stack only)."); }
  };

  // The mission holding the one-reality slot right now — running, or parked
  // at the human boundary. It gets the top of the board: when the system
  // opened it itself, this is how the Studio Head finds out.
  const activeMission = items.find(
    (i) => ACTIVE.has(i.status) || i.status === "AWAITING_AUTHORIZATION"
  ) ?? null;

  // Cheap fingerprint of everything a poll can change; the header dot flickers
  // only when this actually moves, so the heartbeat never lies.
  const heartbeat = `${items.length}|${detail?.status ?? ""}|${detail?.stages.length ?? 0}|${events.length}`;

  return (
    <main>
      <header className="masthead">
        <div>
          <h1>GENESIS OS — OPERATIONAL INTELLIGENCE</h1>
          <div className="sub">Convergence Studios · Operations · Grafana track</div>
          {/* The streamer plate. LIVE means actually live (the dot is the
              real heartbeat); the numbers are the career, folded from
              finished investigations. No fake audience — the only viewers
              are the Studio Head and the judges. */}
          <div className="streamer-plate mono" role="status">
            <span className="live-dot" aria-hidden="true" />
            LIVE — protecting the render farm
            {career && career.resolved > 0 && (
              <> · {career.resolved} saves{career.streak > 1 ? ` · streak ${career.streak}` : ""}</>
            )}
          </div>
        </div>
        <div className="row">
          <button className="btn" onClick={triggerIncident} title="Degrade the render-farm simulator">
            ⚡ Simulate incident
          </button>
          <span className="mode">
            <Pulse signal={heartbeat} />{" "}
            {status
              ? `Grafana MCP ${proofState(status.runtime_proof, "grafana", status.grafana_live)} · Gemini ${proofState(status.runtime_proof, "gemini", status.gemini_live)}`
              : "backend offline"}
          </span>
        </div>
      </header>

      {note && <p className="muted" style={{ marginTop: -8 }}>{note}</p>}

      {/* ══ BAND 1 · THE AGENT — a split mind, thinking in real time.
          No run button anywhere: alerts wake the agent. The left column is
          the cognition ledger (real prompts, real replies, recorded at call
          time); the right column is perception — every Grafana MCP retrieval
          the thinking was based on. Two feeds, one loop, nothing
          reconstructed. */}
      <Section
        id="agent"
        className="band band-agent"
        title="The agent — thinking in real time"
        meta="left: cognition, from the ledger · right: what it saw, through Grafana MCP"
      >
        {activeMission ? (
          <ActiveMission
            item={activeMission}
            selected={selected === activeMission.id}
            busy={busy}
            onOpen={() => setSelected(activeMission.id)}
            onDecide={async (d) => {
              setBusy(true);
              try {
                await decideInvestigation(activeMission.id, d);
                setSelected(activeMission.id);
                setNote(`Decision "${d}" accepted — remediation ${d === "approved" ? "executing" : "declined"}.`);
                await refresh();
              } catch (err) {
                setNote(`Decision failed: ${String(err).slice(0, 160)}`);
              } finally { setBusy(false); }
            }}
          />
        ) : (
          <p className="agent-idle">
            <span className="idle-dot" aria-hidden="true" />
            Listening. When the farm&apos;s health drops, Grafana&apos;s alerts wake the agent —
            there is no run button, and that is the point.
          </p>
        )}
        <PlaysShelf />
        <div className="mind-split">
          <MindStream activeRef={activeMission?.id ?? selected ?? ""} />
          <PerceptionTicker />
        </div>
        {detail && <Detail detail={detail} events={events} busy={busy} onDecide={decide} />}
        <Section
          id="investigations"
          title="History"
          meta={`${items.length} investigation${items.length === 1 ? "" : "s"}`}
          defaultOpen={false}
        >
          <div className="history-rail">
            {items.map((i) => (
              <div key={i.id}
                   className={`item alive-lift ${selected === i.id ? "sel" : ""}`}
                   onClick={() => setSelected(selected === i.id ? null : i.id)}>
                <div className="q">{i.question}</div>
                <div className="meta">
                  <StatusChip status={i.status} />
                  <SeverityChip severity={i.severity} />
                  {i.escalated && <span className="chip warn">! ESCALATED</span>}
                  <button
                    className="item-clear"
                    title={ACTIVE.has(i.status) ? "End this run and remove it" : "Remove this investigation"}
                    aria-label={`Clear investigation: ${i.question}`}
                    onClick={(e) => { e.stopPropagation(); clear(i.id); }}
                  >
                    ✕
                  </button>
                </div>
              </div>
            ))}
            {items.length === 0 && <p className="muted">Nothing yet — the first alert will change that.</p>}
          </div>
        </Section>
      </Section>


      {/* ══ BAND 2 · THE WORLD — the render farm and the five shows it is
          rendering. Measurement, not judgement: everything here is the farm's
          own state, kept visually apart from what the agent concluded. */}
      <Section
        id="world"
        className="band band-world"
        title="The world — Convergence Studios' render farm"
        meta="the farm's own numbers · five shows against their dates"
      >
        <div className="world-split">
          <div><SlateBoard /></div>
          <div><FarmFloor /></div>
        </div>
      </Section>

      {/* ══ BAND 3 · HEALTH — Grafana's view of the farm. Health is not a
          synthetic score: it is these signals against the exact thresholds
          the alert rules fire on. When health drops, the alerts wake the
          agent — that is the whole loop's first domino. And the third room
          is the mirror: Grafana watching the agent work on the farm, the
          way the agent works on the farm. */}
      <Section
        id="health"
        className="band band-perception"
        title="Health — Grafana watching the render farm"
        meta="when health drops, the alerts wake the agent · thresholds drawn where the rules fire"
      >
        <OpsWall />
        <div className="dash-row">
          <span className="muted">The Grafana rooms — health:</span>
          <a href="http://localhost:3001/d/the-slate" target="_blank" rel="noreferrer">The Slate ↗</a>
          <a href="http://localhost:3001/d/farm-floor" target="_blank" rel="noreferrer">Farm Floor ↗</a>
          <span className="muted">· the mirror:</span>
          <a href="http://localhost:3001/d/the-agent" target="_blank" rel="noreferrer">The Agent ↗</a>
          <span className="muted dash-note">— Grafana watching the agent watch the farm: every Gemini call, every token, every MCP retrieval.</span>
        </div>
      </Section>

      <RuntimeBar items={proofItems(status?.runtime_proof, [
        ["gemini", "Gemini"],
        ["grafana", "Grafana MCP"],
        ["temporal", "Temporal"],
        ["datahub", "DataHub"],
      ])} />
    </main>
  );
}

/* ── the split mind ──────────────────────────────────────────────────────
   Left: cognition — the ledger of real Gemini calls, recorded at call time
   with role, latency, tokens, and a preview of the actual reply. Right:
   perception — every Grafana MCP retrieval, with a one-line honest caption
   of what came back. Together they are the thought and the sight it stood on. */

const ROLE_WORD: Record<string, string> = {
  correlation_hypothesis: "correlating signals",
  diagnosis: "weighing diagnoses",
  risk_projection: "projecting the risk",
  remediation_plan: "drafting the remediation",
};

function MindStream({ activeRef }: { activeRef: string }) {
  const [rows, setRows] = useState<import("@/lib/api").CognitionRecord[]>([]);
  // One line per thought; the full reply only on request. The ledger is a
  // ticker to glance at, not a document to scroll past.
  const [openId, setOpenId] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    const load = () => getCognition(18).then((r) => alive && setRows(r)).catch(() => {});
    load();
    const t = setInterval(load, 2500);
    return () => { alive = false; clearInterval(t); };
  }, []);
  const calls = rows.length;
  const tokens = rows.reduce((n, r) => n + (r.tokens?.total ?? 0), 0);
  const cost = rows.reduce((n, r) => n + ((r.tokens?.prompt ?? 0) * 0.075 + Math.max(0, (r.tokens?.total ?? 0) - (r.tokens?.prompt ?? 0)) * 0.3) / 1e6, 0);
  return (
    <div className="mind">
      <div className="feed-head">
        <span className="feed-title">◈ COGNITION — the agent thinking</span>
        <span className="feed-vitals mono" title="From the last 18 recorded model calls — also on The Agent dashboard, where Grafana watches the watcher">
          {calls} calls · {tokens.toLocaleString()} tok · ~${cost.toFixed(4)}
        </span>
      </div>
      <div className="feed" aria-live="polite" aria-label="The agent's model calls, newest first">
        {rows.length === 0 && <p className="muted">No thoughts yet — the ledger fills the moment an alert wakes the loop.</p>}
        {rows.map((r) => {
          const open = openId === r.id;
          return (
            <button key={r.id} type="button"
                    className={`thought ${r.ref && r.ref === activeRef ? "current" : ""} ${r.error ? "errored" : ""} ${open ? "open" : ""}`}
                    aria-expanded={open}
                    onClick={() => setOpenId(open ? null : r.id)}>
              <span className="thought-line">
                <span className="thought-role">{ROLE_WORD[r.role] ?? r.role.replaceAll("_", " ")}</span>
                <span className="thought-text">{r.error ? r.error : r.preview || "…"}</span>
                <span className="thought-meta mono">
                  {r.ms}ms{r.tokens?.total ? ` · ${r.tokens.total}t` : ""}{r.error ? " · FAILED" : ""}
                </span>
              </span>
              {open && (
                <span className="thought-full">
                  {r.error ? r.error : r.preview}
                  {r.ref && <span className="thought-ref mono">{r.ref}</span>}
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function PerceptionTicker() {
  const [rows, setRows] = useState<import("@/lib/api").PerceptionRecord[]>([]);
  useEffect(() => {
    let alive = true;
    const load = () => getPerception(24).then((r) => alive && setRows(r)).catch(() => {});
    load();
    const t = setInterval(load, 2500);
    return () => { alive = false; clearInterval(t); };
  }, []);
  return (
    <div className="sense">
      <div className="feed-head">
        <span className="feed-title">◇ PERCEPTION — what it saw, through Grafana MCP · the same trail the mirror records</span>
        <span className="feed-vitals mono">{rows.length ? `${rows.length} retrievals` : ""}</span>
      </div>
      <div className="feed" aria-label="Grafana MCP retrievals, newest first">
        {rows.length === 0 && <p className="muted">No retrievals yet — every number the agent knows will appear here first.</p>}
        {rows.map((r, i) => (
          <div key={`${r.at}-${i}`} className={`sight ${r.ok ? "" : "errored"}`}>
            <span className="sight-tool mono">{r.tool}</span>
            <span className="sight-note">{r.note || (r.ok ? "returned" : "failed")}</span>
            <span className="sight-ms mono">{r.ms}ms</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* The operations wall assembly: KPI headlines, the five-show risk chart with
   its labelled zero line, and single-hue strips for the core signals. */
function OpsWall() {
  const { buf, slate } = useTelemetryHistory();
  const times = buf.map((s) => s.t);
  if (buf.length === 0) return <p className="muted">Sampling the farm…</p>;
  const latest = buf[buf.length - 1];
  return (
    <>
      <div className="kpi-row">
        <StatTile label="Render queue" value={latest.queue} unit=" jobs"
                  series={buf.map((s) => s.queue)} betterWhenDown />
        <StatTile label="GPU utilization" value={latest.gpu} unit="%"
                  series={buf.map((s) => s.gpu)} betterWhenDown={false} />
        <StatTile label="Job latency" value={latest.latency} unit="s"
                  series={buf.map((s) => s.latency)} betterWhenDown />
        <StatTile label="Shows projected late" unit=""
                  value={slate ? slate.titles.filter((t) => t.risk_hours > 0).length : 0}
                  series={buf.map((s) => Object.values(s.risks).filter((r) => r > 0).length)}
                  betterWhenDown />
      </div>
      {slate && buf.length > 1 && <RiskLines buf={buf} slate={slate} />}
      <div className="strip-row">
        <Strip title="Queue depth" unit=" jobs" series={buf.map((s) => s.queue)}
               times={times} threshold={120} />
        <Strip title="GPU utilization" unit="%" series={buf.map((s) => s.gpu)}
               times={times} threshold={90} />
        <Strip title="Job latency" unit="s" series={buf.map((s) => s.latency)}
               times={times} threshold={6} />
      </div>
    </>
  );
}

/* The mission holding the one-reality slot, at the top of the board where a
   Studio Head cannot miss it. Most of the time the system opened it itself —
   an alert fired, the loop ran — and this is the hand-off point: when it
   parks at the human boundary, the decision buttons are right here. */
function ActiveMission({ item, selected, busy, onOpen, onDecide }: {
  item: InvestigationSummary; selected: boolean; busy: boolean;
  onOpen: () => void; onDecide: (d: "approved" | "rejected") => void;
}) {
  const awaiting = item.status === "AWAITING_AUTHORIZATION";
  const fromAlert = item.question.startsWith("ALERT");
  return (
    <div className={`mission alive-raised ${awaiting ? "awaiting" : ""}`} role="status"
         aria-label={awaiting ? "Active mission awaiting your decision" : "Active mission in progress"}>
      <div className="mission-head">
        <span className="mission-flag">
          {awaiting ? "◉ ACTIVE MISSION — YOUR DECISION IS THE NEXT STEP" : "◉ ACTIVE MISSION"}
        </span>
        <StatusChip status={item.status} />
        {fromAlert && <span className="chip crit">⚡ opened by a firing alert</span>}
      </div>
      <button className="mission-q" onClick={onOpen} title="Open this investigation">
        {item.question}
      </button>
      {item.leading_cause && <div className="mission-cause">{item.leading_cause}</div>}
      <div className="row" style={{ marginTop: 8 }}>
        {awaiting ? (
          <>
            <button className="btn approve" disabled={busy} onClick={() => onDecide("approved")}>
              ✓ Approve remediation
            </button>
            <button className="btn reject" disabled={busy} onClick={() => onDecide("rejected")}>
              ✕ Reject
            </button>
            {!selected && <button className="btn" onClick={onOpen}>Review the evidence →</button>}
          </>
        ) : (
          !selected && <button className="btn" onClick={onOpen}>Watch it work →</button>
        )}
      </div>
    </div>
  );
}

function Detail({ detail, events, busy, onDecide }: {
  detail: InvestigationDetail; events: EventRecord[]; busy: boolean;
  onDecide: (d: "approved" | "rejected") => void;
}) {
  // Stage rows show one truncated line each; a click opens the full detail.
  const [openStage, setOpenStage] = useState<number | null>(null);
  const leading = detail.diagnoses.find((h) => h.id === detail.leading_diagnosis_id) ?? detail.diagnoses[0];
  const running = ACTIVE.has(detail.status);
  const resolved = detail.status === "REMEDIATED";
  const awaiting = detail.status === "AWAITING_AUTHORIZATION";
  const metrics = detail.evidence.filter((e) => e.kind === "metric");
  const logEv = detail.evidence.find((e) => e.kind === "log");
  const alertEv = detail.evidence.find((e) => e.kind === "alert");
  const stageSet = new Set(detail.stages.map((s) => s.name));
  if (detail.plan?.decision) stageSet.add("AUTHORIZE");
  const step = STATUS_STEP[detail.status] ?? null;

  return (
    <>
      <div className={`panel incident alive-raised ${resolved ? "resolved" : ""}`}>
        <div className="row" style={{ justifyContent: "space-between" }}>
          <h2>Operational incident {running && <span className="muted">· investigating…</span>}</h2>
          <StatusChip status={detail.status} />
        </div>
        <VoiceLine line={voiceFor(VOICE, detail.status)} thinking={running} />
        {detail.trigger && detail.trigger.source === "grafana-alert" && (
          <div className="trigger-banner">
            <span className="trigger-flag">⚡ OPENED BY A FIRING ALERT</span>
            <span className="trigger-name">{detail.trigger.alertname}</span>
            {detail.trigger.summary && <span className="muted"> — {detail.trigger.summary}</span>}
            {detail.trigger.incident_id && (
              <span className="chip accent" title="Grafana IRM incident opened for this loop">
                IRM incident {detail.trigger.incident_id}
              </span>
            )}
          </div>
        )}
        {detail.escalated && <Note>HUMAN REVIEW FLAGGED — {detail.escalation_reason || "competing diagnoses too close to call"}</Note>}
        {detail.error && <Note tone="bad">{detail.error}</Note>}
        {leading ? (
          <>
            <div className="cause"><Stream text={leading.cause} /></div>
            <div className="impact">{detail.projection ? `${detail.projection.event} · ${detail.projection.at_risk}` : ""}</div>
            <div className="kv">
              <span className="k">Severity</span><span><SeverityChip severity={leading.severity} /></span>
              <span className="k">Affected</span><span>{leading.affected || detail.scope.slice(-1)[0]}</span>
              <span className="k">Scope</span><span className="muted">{detail.scope.join(" → ")}</span>
            </div>
            <div className="meter" role="img" aria-label={`Confidence ${Math.round(leading.confidence * 100)} percent`}>
              <div style={{ width: `${Math.round(leading.confidence * 100)}%` }} />
            </div>
            <div className="meter-label">{Math.round(leading.confidence * 100)}% confidence · grounded in {detail.evidence.length} telemetry evidence items via Grafana MCP</div>
          </>
        ) : (
          <p className="muted">{running ? "Agents are gathering telemetry…" : "No diagnosis (system healthy)."}</p>
        )}
        {detail.plan && (
          <>
            <div className="kv" style={{ marginTop: 12 }}>
              <span className="k">Recommended</span><span style={{ fontWeight: 700 }}><Stream text={detail.plan.action} /></span>
              <span className="k">Expected</span><span>{detail.plan.expected_effects.join(" · ")}</span>
              <span className="k">Risk</span><span><SeverityChip severity={detail.plan.risk} /></span>
            </div>
            <div className="row" style={{ marginTop: 10 }}>
              {awaiting && !detail.plan.decision ? (
                <>
                  <button className="btn approve" disabled={busy} onClick={() => onDecide("approved")}>✓ Approve remediation</button>
                  <button className="btn reject" disabled={busy} onClick={() => onDecide("rejected")}>✕ Reject</button>
                </>
              ) : detail.plan.decision ? (
                <span className="chip accent">Studio Head decision: {detail.plan.decision.toUpperCase()}</span>
              ) : null}
            </div>
          </>
        )}
      </div>

      {detail.verification && (
        <Verification verification={detail.verification} />
      )}

      {(detail.annotations_written?.length ?? 0) > 0 && (
        <p className="ann-trail">
          <span className="muted">The agent signed its work on the Grafana dashboards: </span>
          {detail.annotations_written!.map((tag) => (
            <span className="chip ann" key={tag}>{tag}</span>
          ))}
        </p>
      )}

      {/* Count the loop's own steps, not every recorded stage: stages include
          names outside the eight-step loop, which read as "10 of 8". */}
      <Section id="loop" title="Operational loop"
               meta={`${LOOP.filter((s) => stageSet.has(s)).length} of ${LOOP.length} steps reached`}>
        <div className="row" style={{ marginBottom: 8 }}>
          {LOOP.map((s) => {
            const reached = stageSet.has(s) || (s === "VERIFY" && detail.verification);
            const here = s === step;
            // Shimmer only while the agents are actually working. AWAITING_AUTHORIZATION
            // is the current step but nothing is running — it waits on you, not on us.
            const working = here && running;
            return (
              <span key={s} className={`chip ${reached || here ? "accent" : ""}${working ? " alive-active" : ""}`}>
                {s}
                {working && <Elapsed stage={detail.status} running={running} />}
              </span>
            );
          })}
        </div>
        <ul className="timeline postmortem alive-cascade">
          {detail.stages.map((s, i) => {
            const at = new Date(s.at);
            // Duration is the gap to the next stage; the last stage has no
            // successor yet, so it shows none rather than a made-up number.
            const next = detail.stages[i + 1];
            const held = next ? (new Date(next.at).getTime() - at.getTime()) / 1000 : null;
            return (
              <li key={`${s.name}-${s.at}`} style={cascade(i)}
                  className={openStage === i ? "open" : ""}
                  onClick={() => setOpenStage(openStage === i ? null : i)}>
                <span className="t-at">{at.toLocaleTimeString()}</span>
                <span className="t-name">{s.name}</span>
                <span className="t-held">{held !== null ? `+${held.toFixed(1)}s` : "—"}</span>
                <span className="t-detail">{s.detail}</span>
              </li>
            );
          })}
        </ul>
        {detail.stages.length > 1 && (
          <div className="postmortem-total">
            {(() => {
              const first = new Date(detail.stages[0].at).getTime();
              const last = new Date(detail.stages[detail.stages.length - 1].at).getTime();
              return `${detail.stages.length} stages · ${((last - first) / 1000).toFixed(1)}s from first observation to last transition`;
            })()}
          </div>
        )}
      </Section>

      {detail.diagnoses.length > 0 && (
        <Section id="hypotheses" title="Competing hypotheses"
                 meta={`${detail.diagnoses.length} considered`}>
          {detail.diagnoses.map((h) => (
            <div className="hyp" key={h.id}>
              <div className="head">
                <span className="conf">{Math.round(h.confidence * 100)}%</span>
                <SeverityChip severity={h.severity} />
                <span>{h.cause}</span>
              </div>
              {h.contradiction_notes && <div className="contra">⚠ contradicts: {h.contradiction_notes}</div>}
            </div>
          ))}
          {detail.correlation && (
            <p className="muted" style={{ fontSize: 12 }}>
              Correlation {detail.correlation.validated ? "validated" : "not validated"}: {detail.correlation.chain.join(" → ")}
            </p>
          )}
        </Section>
      )}

      {metrics.length > 0 && (
        <Section id="evidence" title="Telemetry evidence — retrieved through Grafana MCP"
                 meta={`${metrics.length} signals, ${metrics.filter((e) => e.anomalous).length} anomalous`}>
          <div className="sig alive-cascade">
            {metrics.map((e, i) => (
              <div className="cell" key={e.id} style={cascade(i)}>
                <div className="n">{e.name.replaceAll("_", " ")}</div>
                <div className="v">{e.latest ?? "—"}<span className="s"> {e.unit}</span></div>
                <div className="s">slope {e.slope_per_min ?? "—"}/min</div>
                <Sparkline samples={e.samples} anomalous={e.anomalous}
                           label={e.name.replaceAll("_", " ")} />
                <AnomChip anomalous={e.anomalous} />
                {e.link && (
                  <a className="ev-link" href={e.link} target="_blank" rel="noreferrer"
                     title="Open this signal's panel in Grafana, scoped to the evidence window">
                    View in Grafana ↗
                  </a>
                )}
              </div>
            ))}
          </div>
          {logEv && (
            <>
              <div className="row" style={{ margin: "8px 0 6px" }}>
                <AnomChip anomalous={logEv.anomalous} />
                <span className="muted" style={{ fontSize: 12 }}>{logEv.detail}</span>
              </div>
              <div className="loglines">{logEv.lines.map((l, i) => <div key={i}>{l}</div>)}</div>
            </>
          )}
          {alertEv && <p className="muted" style={{ fontSize: 12, marginBottom: 0 }}>Alerts: {alertEv.lines.join(" · ") || "none"}</p>}
        </Section>
      )}

      <Section id="eventlog" title="Agent event log" defaultOpen={false}
               meta={`${events.length} events`}>
        <div className="log">
          {events.slice(-30).reverse().map((e, i) => (
            <div key={i}><span className="e">{e.event}</span> {summarize(e)}</div>
          ))}
          {events.length === 0 && <span className="muted">No events yet.</span>}
        </div>
      </Section>
    </>
  );
}

/** The before/after money shot. The direction-of-good comes from the backend's
 *  own `_improved` rule (all three core signals want to fall); a metric outside
 *  that set gets a neutral arrow rather than an invented verdict. */
const LOWER_IS_BETTER = new Set(["gpu_utilization_pct", "render_queue_depth", "render_latency_s"]);
const UNITS: Record<string, string> = {
  gpu_utilization_pct: "%", render_queue_depth: "jobs",
  render_latency_s: "s", worker_error_rate_per_min: "errors/min",
};

function Verification({ verification }: { verification: VerificationResult }) {
  const keys = Object.keys(verification.before);
  return (
    <div className={`panel verify-panel ${verification.improved ? "won" : "lost"}`}>
      <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
        <h2 style={{ marginBottom: 0 }}>Post-action verification — re-queried through Grafana MCP</h2>
        <Stamp on={verification.improved ? "REMEDIATED" : "FAILED"}>
          <span className={`seal ${verification.improved ? "good" : "crit"}`}>
            {verification.improved ? "✓ REMEDIATED" : "✕ NOT REMEDIATED"}
          </span>
        </Stamp>
      </div>

      <div className="verify-grid alive-cascade">
        <div className="col-head" />
        <div className="col-head">before</div>
        <div className="col-head" />
        <div className="col-head">after</div>
        <div className="col-head">delta</div>
        {keys.map((k, i) => {
          const b = verification.before[k];
          const a = verification.after[k];
          const unit = UNITS[k] ?? "";
          const decimals = Number.isInteger(b) && Number.isInteger(a ?? 0) ? 0 : 1;
          const known = LOWER_IS_BETTER.has(k);
          const fell = a !== undefined && a < b;
          const better = known && fell;
          const worse = known && a !== undefined && a > b;
          return (
            <Fragment key={k}>
              <div className="metric" style={cascade(i)}>{k.replaceAll("_", " ")}</div>
              <div className="big before" style={cascade(i)}>
                {b.toFixed(decimals)}<span className="u">{unit}</span>
              </div>
              <div className="arrow" style={cascade(i)} aria-hidden="true">→</div>
              <div className="big after" style={cascade(i)}>
                {a === undefined
                  ? <span className="pending">…</span>
                  : <><Rolling value={a} from={b} decimals={decimals} /><span className="u">{unit}</span></>}
              </div>
              <div className={`delta ${better ? "good" : worse ? "crit" : ""}`} style={cascade(i)}>
                {a === undefined ? "" : (
                  <>
                    {fell ? "▼" : a > b ? "▲" : "="} {Math.abs(b - a).toFixed(decimals)}
                    {b !== 0 && <span className="pct"> ({Math.round(((a - b) / b) * 100)}%)</span>}
                  </>
                )}
              </div>
            </Fragment>
          );
        })}
      </div>

      {!verification.improved && <Note tone="bad">{verification.notes}</Note>}
    </div>
  );
}

function summarize(e: EventRecord): string {
  const skip = new Set(["event", "at", "investigation_id"]);
  return Object.entries(e)
    .filter(([k, v]) => !skip.has(k) && (typeof v === "string" || typeof v === "number" || typeof v === "boolean"))
    .map(([k, v]) => `${k}=${String(v).slice(0, 55)}`)
    .join(" ");
}
