"use client";
/* The slate — five shows against their dates.

   This is the stakes panel: the reason a queue number matters is that a movie
   misses a date when it climbs. Progress and risk come straight from the
   farm's own accounting (via the API proxy); nothing here is the agent's
   opinion. LATE is red because positive risk-hours means the projection has
   the show past its delivery date at current throughput. */
import { useEffect, useState } from "react";
import { SlateView, getSlate } from "@/lib/api";

const STATUS_CLASS: Record<string, string> = {
  "LATE": "late", "TIGHT": "tight", "ON TRACK": "ontrack",
};

function riskLabel(h: number): string {
  const a = Math.abs(h);
  const t = a >= 10 ? a.toFixed(0) : a.toFixed(1);
  return h > 0 ? `${t}h late` : `${t}h margin`;
}

export function SlateBoard() {
  const [slate, setSlate] = useState<SlateView | null>(null);
  const [err, setErr] = useState(false);

  useEffect(() => {
    const load = () => getSlate().then((s) => { setSlate(s); setErr(false); })
      .catch(() => setErr(true));
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, []);

  if (err) return <p className="muted">The slate is unreachable — the farm may be down.</p>;
  if (!slate) return <p className="muted">Reading the slate…</p>;

  return (
    <div className="slate">
      {slate.dailies_surge && (
        <p className="slate-surge">Dailies surge in progress — departments are batching tonight&apos;s work in.</p>
      )}
      <div className="slate-rows">
        {slate.titles.map((t) => (
          <div className="slate-row" key={t.key}>
            <div className="slate-name">
              <b>{t.name}</b>
              <span className="muted"> · {t.kind}</span>
            </div>
            <div className="slate-bar" role="img"
                 aria-label={`${t.name} ${(t.progress * 100).toFixed(1)}% complete`}>
              <div className="slate-fill" style={{ width: `${Math.max(0.5, t.progress * 100)}%` }} />
            </div>
            <div className="slate-nums mono">
              {(t.progress * 100).toFixed(1)}% · {t.throughput_fpm.toFixed(0)} f/min
            </div>
            <span className={`slate-chip ${STATUS_CLASS[t.status] ?? ""}`}
                  title={`due in ${t.due_hours.toFixed(1)} sim-hours · projected ${riskLabel(t.risk_hours)}`}>
              {t.status} · {riskLabel(t.risk_hours)}
            </span>
          </div>
        ))}
      </div>
      {slate.hot_shots.length > 0 && (
        <p className="slate-hot muted">
          Longest waiting:{" "}
          {slate.hot_shots.slice(0, 3).map((h) =>
            `${h.show}/${h.shot}${h.retake ? " (retake)" : ""}`).join(" · ")}
        </p>
      )}
    </div>
  );
}
