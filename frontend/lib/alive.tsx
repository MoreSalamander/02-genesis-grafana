"use client";
/* Genesis OS — alive.tsx · the behavior primitives behind alive.css.

   VENDORED, NOT SHARED — copied verbatim into every console (independence
   rule). Zero dependencies beyond React itself, which every console already
   has; the spec's "vanilla" intent is kept by adding no package and holding
   the whole layer to one file per repo.

   Hard rule from UI-ALIVE-SPEC §2: never animate work that isn't happening.
   Every timer here is driven by an actual in-flight flag from the API. */

import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";

/* ── prefers-reduced-motion ─────────────────────────────────────────────── */

export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const sync = () => setReduced(mq.matches);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);
  return reduced;
}

/* ── Cascade — style={cascade(i)} on each child of .alive-cascade ────────── */

export function cascade(index: number): CSSProperties {
  return { "--alive-i": index } as CSSProperties;
}

/* ── The cognition pulse ────────────────────────────────────────────────── */

/** True for ~620ms each time `signal` changes — an honest "this poll returned
 *  something new" beat. Feed it a cheap fingerprint of the polled payload. */
export function useHeartbeat(signal: string | number): boolean {
  const [beat, setBeat] = useState(false);
  const seen = useRef(signal);
  useEffect(() => {
    if (seen.current === signal) return;
    seen.current = signal;
    setBeat(true);
    const t = setTimeout(() => setBeat(false), 620);
    return () => clearTimeout(t);
  }, [signal]);
  return beat;
}

export function Pulse({ signal, title }: { signal: string | number; title?: string }) {
  const beat = useHeartbeat(signal);
  return (
    <span
      className={`alive-pulse${beat ? " beat" : ""}`}
      title={title ?? "system heartbeat — flickers when a poll returns changed data"}
      aria-hidden="true"
    />
  );
}

/* ── Elapsed clock on the active stage ──────────────────────────────────── */

/** Seconds (to a tenth) that `stage` has been the active stage. Resets when
 *  the stage changes; stops dead when `running` goes false, so a finished
 *  console never shows a ticking clock. */
export function useStageClock(stage: string | null, running: boolean): number {
  const [elapsed, setElapsed] = useState(0);
  const startedAt = useRef<number | null>(null);

  useEffect(() => {
    if (!running || !stage) {
      startedAt.current = null;
      setElapsed(0);
      return;
    }
    startedAt.current = Date.now();
    setElapsed(0);
    const t = setInterval(() => {
      if (startedAt.current === null) return;
      setElapsed((Date.now() - startedAt.current) / 1000);
    }, 100);
    return () => clearInterval(t);
  }, [running, stage]);

  return elapsed;
}

export function Elapsed({ stage, running }: { stage: string | null; running: boolean }) {
  const seconds = useStageClock(stage, running);
  if (!running || !stage) return null;
  return <span className="alive-elapsed">{seconds.toFixed(1)}s</span>;
}

/* ── Numbers roll ───────────────────────────────────────────────────────── */

export function Rolling({
  value,
  from,
  decimals = 0,
  prefix = "",
  suffix = "",
  duration = 400,
}: {
  value: number;
  /** Start the roll here instead of at `value` — used for before→after
   *  reveals, where the point is watching the number travel. */
  from?: number;
  decimals?: number;
  prefix?: string;
  suffix?: string;
  duration?: number;
}) {
  const reduced = useReducedMotion();
  const [shown, setShown] = useState(from ?? value);
  const shownRef = useRef(from ?? value);

  useEffect(() => {
    // A hidden tab does not run rAF, so an un-animated number would sit on the
    // old value indefinitely. Correctness beats motion: snap, don't lie.
    if (reduced || (typeof document !== "undefined" && document.hidden)) {
      shownRef.current = value;
      setShown(value);
      return;
    }
    const start = shownRef.current;
    if (start === value) return;
    const t0 = performance.now();
    let raf = 0;
    const tick = (now: number) => {
      const p = Math.min(1, (now - t0) / duration);
      const eased = 1 - Math.pow(1 - p, 3);
      const next = start + (value - start) * eased;
      shownRef.current = next;
      setShown(next);
      if (p < 1) raf = requestAnimationFrame(tick);
      else shownRef.current = value;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, duration, reduced]);

  return (
    <span style={{ fontVariantNumeric: "tabular-nums" }}>
      {prefix}
      {shown.toFixed(decimals)}
      {suffix}
    </span>
  );
}

/* ── Verdicts stamp ─────────────────────────────────────────────────────── */

/** Replays the stamp whenever `on` changes — `key` remounts the subtree, so
 *  the animation fires exactly once per new verdict, never on a bare poll. */
export function Stamp({
  on,
  className = "",
  children,
}: {
  on: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div key={on} className={`alive-stamp ${className}`.trim()}>
      {children}
    </div>
  );
}

/* ── Streaming text — cognition, not a database read ────────────────────── */

export function Stream({
  text,
  wordMs = 28,
  className = "",
}: {
  text: string;
  wordMs?: number;
  className?: string;
}) {
  const reduced = useReducedMotion();
  // Split keeping whitespace so spacing survives; two tokens ≈ one word.
  const tokens = useMemo(() => text.split(/(\s+)/), [text]);
  const [shown, setShown] = useState(0);
  const [skipped, setSkipped] = useState(false);

  useEffect(() => {
    setSkipped(false);
    setShown(0);
  }, [text]);

  useEffect(() => {
    // Same rule as Rolling: no rAF in a hidden tab, so show the whole text
    // rather than leaving a paragraph half-revealed.
    if (reduced || skipped || (typeof document !== "undefined" && document.hidden)) {
      setShown(tokens.length);
      return;
    }
    const step = Math.max(8, wordMs / 2);
    const t0 = performance.now();
    let raf = 0;
    const tick = (now: number) => {
      const n = Math.floor((now - t0) / step);
      setShown(Math.min(n, tokens.length));
      if (n < tokens.length) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [tokens, wordMs, reduced, skipped]);

  const done = shown >= tokens.length;
  return (
    <span
      className={`alive-stream ${className}`.trim()}
      data-streaming={done ? "false" : "true"}
      onClick={() => setSkipped(true)}
      title={done ? undefined : "click to reveal"}
    >
      {tokens.slice(0, shown).join("")}
      {!done && <span className="alive-caret" />}
    </span>
  );
}

/* ── Cold-open empty state (UX P1 #2) ───────────────────────────────────── */

export function EmptyState({
  eyebrow,
  title,
  lead,
  action,
}: {
  eyebrow: string;
  title: string;
  lead: string;
  action?: ReactNode;
}) {
  return (
    <div className="alive-empty">
      <div className="eyebrow">{eyebrow}</div>
      <h3>{title}</h3>
      <p className="lead">{lead}</p>
      {action && <div className="alive-cta">{action}</div>}
    </div>
  );
}

/* ── Degraded / incomplete notes ────────────────────────────────────────── */

/** One banner for every honest-degradation message in the fleet.
 *  `warn` = degraded but still running · `bad` = the work stopped · `info` =
 *  a neutral standing note. The glyph carries the meaning alongside the color. */
export function Note({
  tone = "warn",
  children,
}: {
  tone?: "warn" | "bad" | "info";
  children: ReactNode;
}) {
  const glyph = tone === "bad" ? "✕" : tone === "info" ? "·" : "!";
  return (
    <div className={`alive-note ${tone}`} role="status">
      <span className="g" aria-hidden="true">{glyph}</span>
      <span>{children}</span>
    </div>
  );
}

/* ── Runtime-proof footer (UX P1 #3) ────────────────────────────────────── */

export type RuntimeState = "LIVE" | "DEGRADED" | "MOCK" | "IDLE";

export interface RuntimeItem {
  label: string;
  state: RuntimeState;
  /** Why this state — surfaced on hover so the claim is always checkable. */
  note?: string;
}

const GLYPH: Record<RuntimeState, string> = {
  LIVE: "●",
  DEGRADED: "▲",
  MOCK: "○",
  IDLE: "◌",
};

/** Renders exactly what the backend reported and nothing more: a substrate
 *  that was never exercised reads IDLE, never LIVE. */
export function RuntimeBar({ items }: { items: RuntimeItem[] }) {
  if (items.length === 0) return null;
  return (
    <div className="alive-runtime" role="status" aria-label="Runtime substrate proof">
      {items.map((item) => (
        <span
          key={item.label}
          className={`rt ${item.state}`}
          title={item.note ?? `${item.label}: ${item.state}`}
        >
          <span className="g">{GLYPH[item.state]}</span>
          {item.label}
          <span className="s">{item.state}</span>
        </span>
      ))}
    </div>
  );
}

/** Shape of the `runtime_proof` block every Genesis backend adds to /status. */
export interface RuntimeProof {
  [substrate: string]: { state: RuntimeState; note: string };
}

/** Maps a backend runtime_proof block onto footer chips, in the given order.
 *  Unknown or missing substrates are dropped rather than guessed at. */
export function proofItems(
  proof: RuntimeProof | undefined,
  order: [key: string, label: string][],
): RuntimeItem[] {
  if (!proof) return [];
  return order.flatMap(([key, label]) => {
    const entry = proof[key];
    return entry ? [{ label, state: entry.state, note: `${label} — ${entry.note}` }] : [];
  });
}
