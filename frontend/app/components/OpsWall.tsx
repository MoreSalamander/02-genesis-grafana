"use client";
/* The operations wall — the farm's vital signs as real charts.

   Everything here is sampled live from the farm (via the API proxies) into a
   ring buffer that begins when this page opened, and the captions say so:
   "this session's window" is an honest frame, not a pretended history. The
   agent's evidence windows still come through the MCP server; this wall is
   the room's own eyes.

   Dataviz method notes (the skill's checks, applied):
   · Forms by job — KPI stat tiles for headlines; single-hue strips for each
     signal's trend; one categorical multi-line for delivery risk, because
     telling five shows apart is an identity job.
   · The five title hues are categorical slots in FIXED priority order and
     were validated with the palette script against this console's dark
     surface (#141a17): all five checks pass. Slots follow the entity, never
     the rank — a title keeps its hue whatever its status.
   · Marks: 2px lines, recessive grid, thin fills; values and labels wear ink
     tokens, never series color; the zero line on the risk chart is the story
     ("late" begins above it) and is labelled, not just drawn.
   · Hover: crosshair + tooltip on every strip and on the risk chart. */

import { useEffect, useMemo, useRef, useState } from "react";
import { getFarm, getSlate, SlateView } from "@/lib/api";

// Categorical slots, fixed order by slate priority — validated (dark surface).
export const TITLE_HUES: Record<string, string> = {
  "aurora-falls": "#3987e5",
  "ember-line": "#d95926",
  "the-long-static": "#199e70",
  "glass-harbor": "#c98500",
  "signal-and-noise": "#d55181",
};

const POLL_MS = 3000;
const KEEP = 260; // ≈ 13 minutes of samples

interface Sample {
  t: number; queue: number; weighted?: number; gpu: number; latency: number;
  risks: Record<string, number>;
}

export function useTelemetryHistory() {
  const [buf, setBuf] = useState<Sample[]>([]);
  const [slate, setSlate] = useState<SlateView | null>(null);
  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const [farm, sl] = await Promise.all([getFarm(), getSlate()]);
        if (!alive) return;
        setSlate(sl);
        setBuf((old) => [...old.slice(-(KEEP - 1)), {
          t: Date.now(),
          queue: farm.queue, gpu: farm.gpu, latency: farm.latency_s,
          risks: Object.fromEntries(sl.titles.map((x) => [x.key, x.risk_hours])),
        }]);
      } catch { /* a missed sample is a gap, not a fabrication */ }
    };
    tick();
    const h = setInterval(tick, POLL_MS);
    return () => { alive = false; clearInterval(h); };
  }, []);
  return { buf, slate };
}

/* ---------------------------------------------------------------- helpers */

function scale(points: number[], h: number, pad: number, min?: number, max?: number) {
  const lo = min ?? Math.min(...points);
  const hi = max ?? Math.max(...points);
  const span = hi - lo || 1;
  return (v: number) => h - pad - ((v - lo) / span) * (h - pad * 2);
}

function pathOf(xs: number[], ys: number[]): string {
  return xs.map((x, i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${ys[i].toFixed(1)}`).join("");
}

function ago(ms: number): string {
  const m = Math.round(ms / 60000);
  return m <= 0 ? "now" : `−${m}m`;
}

/* ------------------------------------------------------------- stat tile */

export function StatTile({ label, value, unit, series, betterWhenDown }: {
  label: string; value: number; unit: string; series: number[]; betterWhenDown: boolean;
}) {
  const first = series.length > 4 ? series[0] : null;
  const delta = first !== null ? value - first : null;
  const improving = delta !== null && (betterWhenDown ? delta < 0 : delta > 0);
  const W = 92, H = 26;
  const spark = useMemo(() => {
    if (series.length < 2) return "";
    const y = scale(series, H, 2);
    const xs = series.map((_, i) => (i / (series.length - 1)) * W);
    return pathOf(xs, series.map(y));
  }, [series]);
  return (
    <div className="kpi" role="group" aria-label={`${label} ${value}${unit}`}>
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{Number.isInteger(value) ? value : value.toFixed(1)}
        <span className="kpi-unit">{unit}</span></div>
      {delta !== null && Math.abs(delta) > 0.05 && (
        <div className={`kpi-delta ${improving ? "good" : "bad"}`}>
          {delta > 0 ? "▲" : "▼"} {Math.abs(delta) < 10 ? Math.abs(delta).toFixed(1) : Math.round(Math.abs(delta))}{unit}
          <span className="kpi-win"> in window</span>
        </div>
      )}
      <svg className="kpi-spark" width={W} height={H} aria-hidden="true">
        <path d={spark} fill="none" stroke="var(--accent)" strokeWidth="1.5" />
      </svg>
    </div>
  );
}

/* ------------------------------------------------------ single-hue strip */

export function Strip({ title, unit, series, times, threshold, height = 120 }: {
  title: string; unit: string; series: number[]; times: number[];
  threshold?: number; height?: number;
}) {
  const ref = useRef<SVGSVGElement | null>(null);
  const [hover, setHover] = useState<number | null>(null);
  const W = 560, H = height, PAD = 8;
  const lo = Math.min(0, ...series);
  const hi = Math.max(threshold ?? 0, ...series) * 1.08 || 1;
  const y = scale(series, H, PAD, lo, hi);
  const xs = series.map((_, i) => (i / Math.max(1, series.length - 1)) * W);
  const line = series.length > 1 ? pathOf(xs, series.map(y)) : "";
  const area = line ? `${line}L${W},${H - PAD}L0,${H - PAD}Z` : "";
  const iAt = (px: number) => Math.max(0, Math.min(series.length - 1,
    Math.round((px / W) * (series.length - 1))));
  return (
    <div className="strip">
      <div className="strip-head">
        <span className="strip-title">{title}</span>
        <span className="strip-now mono">{series.length ? (Number.isInteger(series.at(-1)!) ? series.at(-1) : series.at(-1)!.toFixed(1)) : "—"}{unit}</span>
      </div>
      <svg
        ref={ref} viewBox={`0 0 ${W} ${H}`} className="strip-svg" role="img"
        aria-label={`${title}, ${series.length} samples this session, latest ${series.at(-1)?.toFixed(1) ?? "none"}${unit}`}
        onMouseLeave={() => setHover(null)}
        onMouseMove={(e) => {
          const box = (e.target as SVGElement).closest("svg")!.getBoundingClientRect();
          setHover(iAt(((e.clientX - box.left) / box.width) * W));
        }}
      >
        <line x1="0" x2={W} y1={H - PAD} y2={H - PAD} className="grid" />
        <line x1="0" x2={W} y1={PAD} y2={PAD} className="grid faint" />
        {threshold !== undefined && (
          <>
            <line x1="0" x2={W} y1={y(threshold)} y2={y(threshold)} className="threshold" />
            <text x={W - 4} y={y(threshold) - 4} className="axis-text" textAnchor="end">
              threshold {threshold}{unit}
            </text>
          </>
        )}
        {area && <path d={area} fill="var(--accent)" opacity="0.10" />}
        {line && <path d={line} fill="none" stroke="var(--accent)" strokeWidth="2" />}
        {hover !== null && series[hover] !== undefined && (
          <g>
            <line x1={xs[hover]} x2={xs[hover]} y1={PAD} y2={H - PAD} className="crosshair" />
            <circle cx={xs[hover]} cy={y(series[hover])} r="4"
                    fill="var(--accent)" stroke="var(--surface)" strokeWidth="2" />
          </g>
        )}
      </svg>
      <div className="strip-axis">
        <span>{times.length ? ago(Date.now() - times[0]) : ""}</span>
        <span>now</span>
      </div>
      {hover !== null && series[hover] !== undefined && (
        <div className="chart-tip" style={{ left: `${(xs[hover] / W) * 100}%` }}>
          <b>{series[hover].toFixed(1)}{unit}</b> · {ago(Date.now() - times[hover])}
        </div>
      )}
    </div>
  );
}

/* -------------------------------------------- delivery risk, five series */

export function RiskLines({ buf, slate }: { buf: Sample[]; slate: SlateView }) {
  const [hover, setHover] = useState<number | null>(null);
  const W = 1160, H = 190, PAD = 10;
  const keys = slate.titles.map((t) => t.key); // priority order = slot order
  const all = buf.flatMap((s) => keys.map((k) => s.risks[k] ?? 0));
  const lo = Math.min(-1, ...all) * 1.1;
  const hi = Math.max(1, ...all) * 1.15;
  const y = scale([], H, PAD, lo, hi);
  const xs = buf.map((_, i) => (i / Math.max(1, buf.length - 1)) * W);
  const iAt = (px: number) => Math.max(0, Math.min(buf.length - 1,
    Math.round((px / W) * (buf.length - 1))));
  const nameOf = (k: string) => slate.titles.find((t) => t.key === k)?.name ?? k;
  return (
    <div className="risk-chart">
      <svg viewBox={`0 0 ${W} ${H}`} className="risk-svg" role="img"
           aria-label="Delivery risk in hours per show over this session's window; values above zero mean a show is projected late"
           onMouseLeave={() => setHover(null)}
           onMouseMove={(e) => {
             const box = (e.target as SVGElement).closest("svg")!.getBoundingClientRect();
             setHover(iAt(((e.clientX - box.left) / box.width) * W));
           }}>
        <rect x="0" y={PAD} width={W} height={Math.max(0, y(0) - PAD)} className="late-zone" />
        <line x1="0" x2={W} y1={y(0)} y2={y(0)} className="zero-line" />
        <text x={6} y={y(0) - 5} className="axis-text late-tag">late ↑</text>
        <text x={6} y={y(0) + 13} className="axis-text margin-tag">margin ↓</text>
        {keys.map((k) => {
          const ys = buf.map((s) => y(s.risks[k] ?? 0));
          if (buf.length < 2) return null;
          return <path key={k} d={pathOf(xs, ys)} fill="none"
                       stroke={TITLE_HUES[k] ?? "var(--accent)"} strokeWidth="2" />;
        })}
        {hover !== null && buf[hover] && (
          <g>
            <line x1={xs[hover]} x2={xs[hover]} y1={PAD} y2={H - PAD} className="crosshair" />
            {keys.map((k) => (
              <circle key={k} cx={xs[hover]} cy={y(buf[hover].risks[k] ?? 0)} r="3.5"
                      fill={TITLE_HUES[k]} stroke="var(--surface)" strokeWidth="2" />
            ))}
          </g>
        )}
      </svg>
      <div className="risk-legend" role="list" aria-label="Shows">
        {slate.titles.map((t) => (
          <span className="risk-key" role="listitem" key={t.key}>
            <i style={{ background: TITLE_HUES[t.key] }} aria-hidden="true" />
            {t.name}
            <b className={`mono ${t.risk_hours > 0 ? "isLate" : ""}`}>
              {t.risk_hours > 0 ? "+" : ""}{t.risk_hours.toFixed(1)}h
            </b>
          </span>
        ))}
      </div>
      {hover !== null && buf[hover] && (
        <div className="chart-tip wide" style={{ left: `${Math.min(86, (xs[hover] / W) * 100)}%` }}>
          <div className="tip-when">{ago(Date.now() - buf[hover].t)}</div>
          {keys.map((k) => (
            <div key={k} className="tip-row">
              <i style={{ background: TITLE_HUES[k] }} aria-hidden="true" />
              {nameOf(k)} <b>{(buf[hover].risks[k] ?? 0).toFixed(2)}h</b>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
