"use client";
import { useCallback, useEffect, useState } from "react";
import {
  ACTIVE, EventRecord, InvestigationDetail, InvestigationSummary, SystemStatus,
  decideInvestigation, getEvents, getInvestigation, getStatus, listInvestigations,
  simulateIncident, startInvestigation,
} from "@/lib/api";
import { AnomChip, SeverityChip, StatusChip } from "./components/Chips";

const DEMO_QUESTION = "How is production doing right now?";
const LOOP = ["OBSERVE", "CORRELATE", "DIAGNOSE", "PREDICT", "RECOMMEND", "AUTHORIZE", "ACT", "VERIFY"];

export default function CommandConsole() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [items, setItems] = useState<InvestigationSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<InvestigationDetail | null>(null);
  const [events, setEvents] = useState<EventRecord[]>([]);
  const [question, setQuestion] = useState(DEMO_QUESTION);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");

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
    try {
      const { id } = await startInvestigation(question.trim());
      setSelected(id);
    } finally { setBusy(false); }
  };

  const decide = async (decision: "approved" | "rejected") => {
    if (!detail || busy) return;
    setBusy(true);
    try { await decideInvestigation(detail.id, decision); await refresh(); }
    finally { setBusy(false); }
  };

  const triggerIncident = async () => {
    try { await simulateIncident(); setNote("Incident injected into the render farm — telemetry is degrading."); }
    catch { setNote("Simulator not reachable (live stack only)."); }
  };

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
            {status ? `Grafana MCP ${status.grafana_live ? "LIVE" : "MOCK"} · Gemini ${status.gemini_live ? "LIVE" : "MOCK"}` : "backend offline"}
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
        <button className="btn approve" onClick={launch} disabled={busy}>Run investigation</button>
      </div>
      {note && <p className="muted" style={{ marginTop: -8 }}>{note}</p>}

      <div className="cmd">
        <aside className="rail">
          <div className="panel">
            <h2>Investigations</h2>
            {items.length === 0 && <p className="muted">None yet — run one above.</p>}
            {items.map((i) => (
              <div key={i.id} className={`item ${selected === i.id ? "sel" : ""}`} onClick={() => setSelected(i.id)}>
                <div className="q">{i.question}</div>
                <div className="meta">
                  <StatusChip status={i.status} />
                  <SeverityChip severity={i.severity} />
                  {i.escalated && <span className="chip warn">! ESCALATED</span>}
                </div>
              </div>
            ))}
          </div>
        </aside>

        <section>
          {!detail ? (
            <div className="panel"><p className="muted">Select an investigation to open the incident view.</p></div>
          ) : (
            <Detail detail={detail} events={events} busy={busy} onDecide={decide} />
          )}
        </section>
      </div>
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

  return (
    <>
      <div className={`panel incident ${resolved ? "resolved" : ""}`}>
        <div className="row" style={{ justifyContent: "space-between" }}>
          <h2>Operational incident {running && <span className="muted">· investigating…</span>}</h2>
          <StatusChip status={detail.status} />
        </div>
        {detail.escalated && <div className="esc">! HUMAN REVIEW FLAGGED — {detail.escalation_reason || "competing diagnoses too close to call"}</div>}
        {detail.error && <div className="esc">! {detail.error}</div>}
        {leading ? (
          <>
            <div className="cause">{leading.cause}</div>
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
              <span className="k">Recommended</span><span style={{ fontWeight: 700 }}>{detail.plan.action}</span>
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
        <div className="panel">
          <h2>Post-action verification — via Grafana MCP {detail.verification.improved ? "· remediation successful" : "· FAILED"}</h2>
          <div className="verify">
            {Object.keys(detail.verification.before).map((k) => {
              const b = detail.verification!.before[k];
              const a = detail.verification!.after[k];
              return (
                <div className="cell" key={k}>
                  <div className="name">{k.replaceAll("_", " ")}</div>
                  <div className="vals">{b} → {a ?? "…"}</div>
                  {a !== undefined && <div className="delta">{a < b ? `▼ ${(b - a).toFixed(1)}` : `▲ ${(a - b).toFixed(1)}`}</div>}
                </div>
              );
            })}
          </div>
          {!detail.verification.improved && <p className="esc" style={{ marginTop: 10 }}>! {detail.verification.notes}</p>}
        </div>
      )}

      <div className="panel">
        <h2>Operational loop</h2>
        <div className="row" style={{ marginBottom: 8 }}>
          {LOOP.map((s) => (
            <span key={s} className={`chip ${stageSet.has(s) || (s === "VERIFY" && detail.verification) ? "accent" : ""}`}>{s}</span>
          ))}
        </div>
        <ul className="timeline">
          {detail.stages.map((s, i) => (
            <li key={i}>
              <span className="t-name">{s.name}</span>
              <span className="t-detail">{s.detail}</span>
            </li>
          ))}
        </ul>
      </div>

      {detail.diagnoses.length > 0 && (
        <div className="panel">
          <h2>Competing hypotheses</h2>
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
        </div>
      )}

      {metrics.length > 0 && (
        <div className="panel">
          <h2>Telemetry evidence — retrieved through Grafana MCP</h2>
          <div className="sig">
            {metrics.map((e) => (
              <div className="cell" key={e.id}>
                <div className="n">{e.name.replaceAll("_", " ")}</div>
                <div className="v">{e.latest ?? "—"}<span className="s"> {e.unit}</span></div>
                <div className="s">slope {e.slope_per_min ?? "—"}/min</div>
                <AnomChip anomalous={e.anomalous} />
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
        </div>
      )}

      <div className="panel">
        <h2>Agent event log</h2>
        <div className="log">
          {events.slice(-30).reverse().map((e, i) => (
            <div key={i}><span className="e">{e.event}</span> {summarize(e)}</div>
          ))}
          {events.length === 0 && <span className="muted">No events yet.</span>}
        </div>
      </div>
    </>
  );
}

function summarize(e: EventRecord): string {
  const skip = new Set(["event", "at", "investigation_id"]);
  return Object.entries(e)
    .filter(([k, v]) => !skip.has(k) && (typeof v === "string" || typeof v === "number" || typeof v === "boolean"))
    .map(([k, v]) => `${k}=${String(v).slice(0, 55)}`)
    .join(" ");
}
