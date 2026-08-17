"use client";
/* Instruments for the render farm.

   Same heads-up language as the signal desk — notched panels, tick marks, thin
   bright strokes — in the ops room's violet on green-black. The discipline is
   the same too: a farm dashboard is the easiest place in this whole system to
   lie, because operators expect dials and will believe them.

   So, the boundaries this file holds to:

     · every metric here is a site-wide aggregate — avg()/max()/sum() over
       site="local". There is no per-node telemetry, so nothing draws a rack of
       individual machines. The farm is drawn as the pipeline a job moves
       through, which is what the data actually describes.
     · a stage lights up only when a diagnosis names it in `affected`, and the
       raw text is shown so the match can be checked.
     · readings are a snapshot over a window, not a live feed. The panel says
       when they were taken.
     · a stream with no reading (an unconfigured datasource) says so, rather
       than drawing a flat line at zero. */

import { TelemetryEvidence, DiagnosisHypothesis } from "@/lib/api";
import { Sparkline } from "./Sparkline";

/* ── panel ───────────────────────────────────────────────────────────────── */

export function Panel({ title, meta, className = "", children }: {
  title?: string;
  meta?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <section className={`hud-panel ${className}`}>
      {title && (
        <header className="hp-head">
          <h2>{title}</h2>
          {meta && <span className="hp-meta">{meta}</span>}
        </header>
      )}
      <div className="hp-body">{children}</div>
    </section>
  );
}

/* ── metric instrument ───────────────────────────────────────────────────── */

/* The metric names are machine-shaped. These are what an operator calls them. */
const METRIC_LABEL: Record<string, string> = {
  gpu_utilization_pct: "GPU utilisation",
  render_queue_depth: "jobs waiting",
  render_latency_s: "time per frame",
  worker_error_rate_per_min: "worker errors",
  worker_error_logs: "error log lines",
  request_traces: "request traces",
  alert_rules: "alerts firing",
};

function reading(v: number | null): string {
  if (v === null || Number.isNaN(v)) return "—";
  return Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(v % 1 === 0 ? 0 : 2);
}

/** One telemetry stream as an instrument: what it reads now, which way it is
 *  moving, and the shape it has been making. Direction is stated as direction —
 *  whether rising is good depends on the metric, and this does not guess. */
export function MetricGauge({ evidence }: { evidence: TelemetryEvidence }) {
  const e = evidence;
  const label = METRIC_LABEL[e.name] ?? e.name.replace(/_/g, " ");
  const has = e.latest !== null && !Number.isNaN(e.latest);
  const slope = e.slope_per_min;
  // Below this the line is flat enough that an arrow would be noise.
  const moving = slope !== null && Math.abs(slope) >= 0.01;
  const dir = !moving ? "flat" : slope! > 0 ? "up" : "down";

  return (
    <div className={`farm-gauge${e.anomalous ? " anomalous" : ""}${has ? "" : " dark"}`}>
      <div className="fg-head">
        <span className="fg-name">{label}</span>
        {e.anomalous && <span className="fg-flag">unusual</span>}
      </div>

      <div className="fg-value">
        <b>{reading(e.latest)}</b>
        {has && <span className="fg-unit">{e.unit}</span>}
      </div>

      {e.samples.length >= 2 ? (
        <Sparkline samples={e.samples} anomalous={e.anomalous} width={190} height={40} label={label} />
      ) : (
        <p className="fg-nodata">
          {has ? "single reading — no series to plot" : e.detail || "no data returned"}
        </p>
      )}

      <div className="fg-foot">
        {moving ? (
          <span className={`fg-trend ${dir}`}>
            {dir === "up" ? "▲" : "▼"} {Math.abs(slope!).toFixed(2)}{e.unit}/min
          </span>
        ) : (
          <span className="fg-trend flat">steady</span>
        )}
        {e.average !== null && <span className="fg-avg">avg {reading(e.average)}</span>}
      </div>
    </div>
  );
}

/* ── the farm as a pipeline ──────────────────────────────────────────────── */

/* A render job moves queue → schedule → render → write. Each stage is bound to
   the metric that actually measures it, so a lit stage always has a number
   behind it. `match` decides whether a diagnosis's free-text `affected` names
   this stage; anything that matches nothing lights nothing. */
const STAGES: { key: string; label: string; metric: string; match: RegExp }[] = [
  { key: "queue", label: "Queue", metric: "render_queue_depth", match: /queue|schedul|backlog|job/i },
  { key: "workers", label: "Worker pool", metric: "gpu_utilization_pct", match: /worker|pool|gpu|node|render worker/i },
  { key: "errors", label: "Failures", metric: "worker_error_rate_per_min", match: /error|fail|oom|memory|crash/i },
  { key: "output", label: "Frames out", metric: "render_latency_s", match: /latency|frame|output|throughput|render time/i },
];

const SEVERITY_RANK: Record<string, number> = { CRITICAL: 3, HIGH: 2, MEDIUM: 1, LOW: 0 };

export function FarmPipeline({ evidence, diagnoses }: {
  evidence: TelemetryEvidence[];
  diagnoses: DiagnosisHypothesis[];
}) {
  const byName = new Map(evidence.map((e) => [e.name, e]));

  return (
    <div className="farm-flow">
      <div className="ff-track" role="list">
        {STAGES.map((stage, i) => {
          const metric = byName.get(stage.metric);
          // Worst severity among diagnoses that name this stage. No match, no
          // colour — the pipeline never invents a hotspot.
          let worst: string | null = null;
          const naming: string[] = [];
          for (const d of diagnoses) {
            if (!stage.match.test(d.affected ?? "")) continue;
            naming.push(d.affected);
            if (worst === null || (SEVERITY_RANK[d.severity] ?? -1) > (SEVERITY_RANK[worst] ?? -1)) {
              worst = d.severity;
            }
          }
          const tone = worst ? worst.toLowerCase() : "";

          return (
            <div className="ff-step" key={stage.key} role="listitem">
              <div
                className={`ff-node ${tone}${metric?.anomalous ? " anomalous" : ""}`}
                title={naming.length ? `named in: ${[...new Set(naming)].join("; ")}` : undefined}
              >
                <span className="ff-label">{stage.label}</span>
                <span className="ff-read">
                  {metric && metric.latest !== null
                    ? <>{reading(metric.latest)}<i>{metric.unit}</i></>
                    : <i className="none">no reading</i>}
                </span>
                {worst && <span className={`ff-sev ${tone}`}>{worst}</span>}
              </div>
              {i < STAGES.length - 1 && <span className="ff-arrow" aria-hidden="true">→</span>}
            </div>
          );
        })}
      </div>
      <p className="ff-note">
        A job moves left to right. A stage is marked only when a diagnosis named it — hover a
        marked stage to see the wording it was named with.
      </p>
    </div>
  );
}

/* ── the correlation chain ───────────────────────────────────────────────── */

/** The chain the system derived, drawn as the causal sequence it claims: this
 *  explains that, which explains the next. These are evidence names it linked
 *  itself — nothing here is inferred by the console. */
export function ChainFlow({ chain, rationale }: { chain: string[]; rationale: string }) {
  if (chain.length === 0) return null;
  return (
    <div className="chain-flow">
      <div className="cf-row">
        {chain.map((name, i) => (
          <span className="cf-step" key={`${name}${i}`}>
            <span className="cf-chip">{METRIC_LABEL[name] ?? name.replace(/_/g, " ")}</span>
            {i < chain.length - 1 && <span className="cf-arrow" aria-hidden="true">→</span>}
          </span>
        ))}
      </div>
      {rationale && <p className="cf-why">{rationale}</p>}
    </div>
  );
}
