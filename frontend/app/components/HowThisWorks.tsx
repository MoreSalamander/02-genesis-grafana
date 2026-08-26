"use client";
/* The first thing a new viewer should read.

   The board assumes you already know what the show is: an operations agent
   protecting a render farm with real observability data, in front of a human
   who holds the only approve button. Said once, plainly, then out of the way. */

import { useEffect, useState } from "react";

const KEY = "genesis.ops.howthisworks.dismissed";

export function HowThisWorks() {
  const [show, setShow] = useState(false);
  useEffect(() => {
    try { setShow(localStorage.getItem(KEY) !== "1"); } catch { setShow(true); }
  }, []);
  const dismiss = () => {
    try { localStorage.setItem(KEY, "1"); } catch { /* private mode — it reappears */ }
    setShow(false);
  };
  if (!show) return null;

  return (
    <section className="how">
      <div className="how-top">
        <h2>What this is</h2>
        <button className="how-x" onClick={dismiss} aria-label="Dismiss">Got it</button>
      </div>

      <p className="how-lead">
        An operations agent protecting a studio&rsquo;s render farm — run as a show. When an
        alert fires, it investigates with the same observability data an engineer would pull,
        proposes a remediation with its evidence attached, waits for a human, acts, and then
        verifies honestly whether the farm actually got better. Wins and losses both go on
        the shelf.
      </p>

      <ol className="how-steps">
        <li>
          <b>Something breaks.</b> Press <i>Simulate incident</i> (or wait — the farm has
          weather). An alert fires on a real dashboard, and the watcher opens an
          investigation on its own.
        </li>
        <li>
          <b>It investigates like an engineer.</b> Logs, traces, metrics, and its own memory
          of past cases — every diagnosis carries deep links back to the evidence, so you can
          check its reading before trusting it.
        </li>
        <li>
          <b>You hold the button.</b> Nothing is remediated until you approve. Then it acts,
          watches the trend actually reverse before claiming success, and records the play —
          fastest fixes and from-memory saves become career records only when they are real.
        </li>
      </ol>

      <p className="how-thesis">
        <b>Failure is recorded, not edited out.</b> The career numbers above the board count
        losses as faithfully as wins, because an operations tool you cannot trust about its
        failures is not one you can trust about its saves.
      </p>

      <details className="how-stack">
        <summary>The stack underneath, and why each piece is here</summary>
        <ul>
          <li><b>Grafana MCP server</b> — the official <i>mcp-grafana</i>, the agent&rsquo;s hands: it queries metrics, logs, and traces, searches dashboards, and writes annotations through the same 60+ tools a human&rsquo;s Grafana speaks.</li>
          <li><b>Grafana Cloud</b> — the judged surface: real dashboards, real alert rules, and the agent&rsquo;s annotations landing where operators would see them.</li>
          <li><b>Prometheus · Loki · Tempo</b> — the farm&rsquo;s telemetry: metrics, logs, and traces the investigation actually reads, cross-linked by trace id.</li>
          <li><b>Self-observation</b> — the agent&rsquo;s own Gemini calls, tokens, and cost land on a dashboard too: observe the agent you build.</li>
          <li><b>Gemini</b> — the cognition: reads evidence, writes the diagnosis and the remediation case. Never marks its own homework — verification is computed from telemetry.</li>
          <li><b>Temporal</b> — act and verify run as durable workflows; a restart cannot orphan a half-applied remediation.</li>
          <li><b>PostgreSQL</b> — the investigation record, shared by every process.</li>
          <li><b>Redis</b> — the one-active-investigation latch: the agent finishes a thought before starting the next.</li>
          <li><b>NATS</b> — the event fabric the live feed tails.</li>
          <li><b>The render-farm simulator</b> — a world that can genuinely break, so saves and failures are earned, not scripted.</li>
        </ul>
        <p className="how-foot">
          The chips in the masthead report what is live <i>right now</i> — LIVE only ever means
          the substrate was actually exercised in this process, never that it is merely configured.
        </p>
      </details>
    </section>
  );
}
