"use client";
/* The clips shelf and the replay player.

   Inside the code the agent is a legend — these are its saved plays, badged
   and titled like a highlight bin. Outside the code it is a program a studio
   head trusts, which is why a replay renders nothing but the recorded
   timeline of a real investigation: real stage timestamps compressed to a
   watchable pace and labelled as exactly that. No fake audience, no fake
   drama: records are only worn where a faster fix actually happened. */

import { useEffect, useMemo, useRef, useState } from "react";
import { PlayRecord, Scoreboard, getPlays, getScoreboard } from "@/lib/api";
import { Rolling, Stamp } from "@/lib/alive";

const RECORD_WORD: Record<string, string> = {
  fastest_fix: "🏆 fastest fix yet",
  fastest_thinking: "🏆 fastest read yet",
  first_memory_win: "🧭 first win from memory",
};

function clock(s: number | null): string {
  if (s === null || s === undefined) return "—";
  if (s < 90) return `${s.toFixed(0)}s`;
  return `${Math.floor(s / 60)}m${String(Math.round(s % 60)).padStart(2, "0")}s`;
}

/* ------------------------------------------------------------- the shelf */

export function PlaysShelf() {
  const [plays, setPlays] = useState<PlayRecord[]>([]);
  const [board, setBoard] = useState<Scoreboard | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    const load = () => Promise.all([getPlays(16), getScoreboard()])
      .then(([p, b]) => { if (alive) { setPlays(p); setBoard(b); } })
      .catch(() => {});
    load();
    const t = setInterval(load, 5000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  const open = plays.find((p) => p.id === openId) ?? null;
  return (
    <div className="plays">
      <div className="plays-head">
        <span className="plays-title">🎬 SAVED PLAYS — the highlight bin</span>
        {board && (
          <span className="career mono" role="group" aria-label="Career record">
            SAVES {board.resolved} · STREAK {board.streak}
            {board.best_fix_s !== null && <> · BEST FIX {clock(board.best_fix_s)}</>}
            {board.recalled_fixes > 0 && <> · FROM MEMORY {board.recalled_fixes}</>}
          </span>
        )}
      </div>
      {board && Object.keys(board.families).length > 0 && (
        <div className="bestiary" aria-label="Incident families faced and beaten">
          {Object.entries(board.families).map(([name, f]) => (
            <span key={name} className={`chip ${f.beaten === f.faced && f.faced > 0 ? "good" : ""}`}>
              {name} {f.beaten}/{f.faced}
            </span>
          ))}
        </div>
      )}
      {plays.length === 0 ? (
        <p className="muted">No plays yet — the first verified save clips itself.</p>
      ) : (
        <div className="plays-shelf" role="list">
          {plays.map((p) => (
            <button key={p.id} role="listitem"
                    className={`play-card ${openId === p.id ? "open" : ""}`}
                    onClick={() => setOpenId(openId === p.id ? null : p.id)}>
              <div className="play-title">{p.title}</div>
              <div className="play-clocks mono">
                read {clock(p.thinking_s)} · fixed {clock(p.fixed_s)}
              </div>
              <div className="play-badges">
                {p.from_alert && <span className="play-badge">⚡ from an alert</span>}
                {p.recalled > 0 && <span className="play-badge">🧭 from memory</span>}
                {p.records.map((r) => (
                  <span key={r} className="play-badge record">{RECORD_WORD[r] ?? r}</span>
                ))}
                {p.streak > 1 && <span className="play-badge">STREAK ×{p.streak}</span>}
              </div>
            </button>
          ))}
        </div>
      )}
      {open && <PlayReplay play={open} onClose={() => setOpenId(null)} />}
    </div>
  );
}

/* ------------------------------------------------------------ the replay */

const REPLAY_STEP_MS = 1100;

export function PlayReplay({ play, onClose }: { play: PlayRecord; onClose: () => void }) {
  const [step, setStep] = useState(0);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const steps = useMemo(() => {
    const t0 = new Date(play.timeline[0]?.at ?? play.at).getTime();
    const rel = (at: string) => Math.max(0, (new Date(at).getTime() - t0) / 1000);
    return play.timeline.map((s) => ({ ...s, t: rel(s.at) }));
  }, [play]);
  const total = steps.length + 1; // +1 for the closing card

  useEffect(() => {
    setStep(0);
    timer.current = setInterval(() => {
      setStep((s) => {
        if (s + 1 >= total && timer.current) clearInterval(timer.current);
        return Math.min(s + 1, total);
      });
    }, REPLAY_STEP_MS);
    return () => { if (timer.current) clearInterval(timer.current); };
  }, [play.id, total]);

  const done = step >= total;
  const metrics = Object.keys(play.after);
  return (
    <div className="replay" role="region" aria-label={`Replay of ${play.title}`}>
      <div className="replay-head">
        <span className="replay-title">{play.title}</span>
        <span className="replay-honest mono">
          replay · recorded {new Date(play.at).toLocaleString()} · compressed time
        </span>
        <button className="btn" onClick={onClose}>close</button>
      </div>
      {play.alertname && (
        <div className={`replay-alert ${step >= 0 ? "on" : ""}`}>
          ⚡ {play.alertname}
        </div>
      )}
      <ol className="replay-steps">
        {steps.map((s, i) => (
          <li key={`${s.name}-${i}`} className={i < step ? "played" : i === step ? "playing" : ""}>
            <span className="rs-t mono">t+{s.t.toFixed(0)}s</span>
            <span className="rs-name">{s.name}</span>
            <span className="rs-detail">{s.detail}</span>
          </li>
        ))}
      </ol>
      {done && (
        <div className="replay-outro">
          <Stamp on={play.id} className="seal good">PLAY SAVED</Stamp>
          <div className="replay-ba">
            {metrics.map((k) => (
              <span key={k} className="ba mono">
                {k.replaceAll("_", " ")}: {play.before[k] ?? "—"} → <b><Rolling value={play.after[k]} /></b>
              </span>
            ))}
          </div>
          {play.action && <div className="replay-action">{play.action}</div>}
        </div>
      )}
    </div>
  );
}
