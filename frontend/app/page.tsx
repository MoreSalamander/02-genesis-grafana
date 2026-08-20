"use client";
import { Fragment, useCallback, useEffect, useState } from "react";
import {
  ACTIVE, EventRecord, InvestigationDetail, InvestigationSummary, SystemStatus,
  VerificationResult,
  decideInvestigation, getEvents, getInvestigation, getStatus, listInvestigations,
  clearInvestigation, simulateIncident, startInvestigation,
} from "@/lib/api";
import { AnomChip, SeverityChip, StatusChip } from "./components/Chips";
import { Sparkline } from "./components/Sparkline";
import { FarmFloor } from "./components/FarmFloor";
import { SlateBoard } from "./components/SlateBoard";
import { Section } from "./components/Section";
import {
  Elapsed, EmptyState, Note, Pulse, Rolling, RuntimeBar, Stamp, Stream, VoiceLine,
  cascade, proofItems, proofState, useCursorGlow, voiceFor,
} from "@/lib/alive";

const DEMO_QUESTION = "How is production doing right now?";
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
  const [question, setQuestion] = useState(DEMO_QUESTION);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  useCursorGlow();

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

  const launch = async () => {
    if (busy || !question.trim()) return;
    setBusy(true);
    setNote("");
    try {
      const { id } = await startInvestigation(question.trim());
      setSelected(id);
    } catch (err) {
      // One operational reality at a time is the design, not a failure. When
      // the slot is held — usually because a firing alert opened its own
      // investigation — the console takes you to that reality instead of
      // printing an error at you. Decide it, and the slot frees.
      const msg = String(err);
      const active = msg.includes("already active") ? msg.match(/inv_[0-9a-f]+/)?.[0] : null;
      if (active) {
        setSelected(active);
        setNote("The farm already has an active investigation — showing it. "
          + "Decide or clear it and the slot frees for your question.");
      } else {
        setNote(`Investigation failed to start: ${msg.slice(0, 200)}`);
      }
    } finally { setBusy(false); }
  };

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

  // Cheap fingerprint of everything a poll can change; the header dot flickers
  // only when this actually moves, so the heartbeat never lies.
  const heartbeat = `${items.length}|${detail?.status ?? ""}|${detail?.stages.length ?? 0}|${events.length}`;
  const coldOpen = items.length === 0 && !detail;

  return (
    <main>
      <header className="masthead">
        <div>
          <h1>GENESIS OS — OPERATIONAL INTELLIGENCE</h1>
          <div className="sub">Convergence Studios · Operations · Grafana track</div>
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

      <div className="cmdbar">
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && launch()}
          placeholder="Ask operations anything…"
          aria-label="Operational question"
        />
        <button className="btn approve alive-track" onClick={launch} disabled={busy}>Run investigation</button>
      </div>
      {note && <p className="muted" style={{ marginTop: -8 }}>{note}</p>}

      {/* The farm itself, above the investigations. This is the world being
          watched — the panels below are what the loop made of it. Keeping the
          two apart is the point: one is measurement, the other is judgement. */}
      {/* The stakes above the machinery: what the farm is FOR. A queue number
          matters because one of these five shows misses its date when it
          climbs — this is the sentence the alerts speak. */}
      <Section
        id="slate"
        className="slate-panel"
        title="The slate — five shows against their dates"
        meta="live from the farm's own accounting"
      >
        <SlateBoard />
      </Section>

      <Section
        id="farm"
        className="farm-panel"
        title="The render farm"
        meta="live from the farm, not from the investigation"
      >
        <FarmFloor />
      </Section>

      <div className="cmd">
        <aside className="rail">
          <Section
            id="investigations"
            className="alive-cascade"
            title="Investigations"
            meta={`${items.length}${items.filter((i) => ACTIVE.has(i.status)).length
              ? ` · ${items.filter((i) => ACTIVE.has(i.status)).length} running` : ""}`}
          >
            {items.length === 0 && <p className="muted">None yet — run one above.</p>}
            {items.map((i, idx) => (
              <div key={i.id} style={cascade(idx)}
                   className={`item alive-lift ${selected === i.id ? "sel" : ""}`}
                   onClick={() => setSelected(i.id)}>
                <div className="q">{i.question}</div>
                <div className="meta">
                  <StatusChip status={i.status} />
                  <SeverityChip severity={i.severity} />
                  {i.escalated && <span className="chip warn">! ESCALATED</span>}
                  <button
                    className="item-clear"
                    title={ACTIVE.has(i.status)
                      ? "End this run and remove it"
                      : "Remove this investigation"}
                    aria-label={`Clear investigation: ${i.question}`}
                    onClick={(e) => { e.stopPropagation(); clear(i.id); }}
                  >
                    ✕
                  </button>
                </div>
              </div>
            ))}
          </Section>
        </aside>

        <section>
          {coldOpen ? (
            <div className="panel">
              <EmptyState
                eyebrow="Operational Intelligence · Grafana track"
                title="The ops room watches the render farm and explains itself."
                lead="Ask it anything about production and it observes live telemetry through the Grafana
                      MCP server, correlates the signals, argues competing diagnoses against each other,
                      predicts what breaks next, and brings you a remediation to authorize — then verifies
                      the fix against the same metrics it used to make the call."
                action={
                  <button className="btn approve" onClick={launch} disabled={busy}>
                    Start here — ask “{DEMO_QUESTION}”
                  </button>
                }
              />
            </div>
          ) : !detail ? (
            <div className="panel"><p className="muted">Select an investigation to open the incident view.</p></div>
          ) : (
            <Detail detail={detail} events={events} busy={busy} onDecide={decide} />
          )}
        </section>
      </div>

      <RuntimeBar items={proofItems(status?.runtime_proof, [
        ["gemini", "Gemini"],
        ["grafana", "Grafana MCP"],
        ["temporal", "Temporal"],
        ["datahub", "DataHub"],
      ])} />
    </main>
  );
}

function Detail({ detail, events, busy, onDecide }: {
  detail: InvestigationDetail; events: EventRecord[]; busy: boolean;
  onDecide: (d: "approved" | "rejected") => void;
}) {
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
              <li key={`${s.name}-${s.at}`} style={cascade(i)}>
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
