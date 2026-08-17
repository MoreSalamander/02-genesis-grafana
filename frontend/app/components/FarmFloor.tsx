"use client";
/* The render farm, live.

   Sixteen workers, the jobs they are holding, and the queue behind them —
   polled straight from the farm rather than reconstructed from the agent's
   findings. That distinction is the whole reason this panel exists: everything
   else in this console is what the loop *concluded*, and this is what is
   actually happening. The two are labelled differently and never merged.

   Every cell is bound to a real worker record. A worker with no job shows no
   job. When the farm cannot be reached the panel says so instead of drawing
   sixteen idle machines, because "idle" and "unknown" are different claims and
   only one of them is true. */

import { useEffect, useRef, useState } from "react";
import { FarmView, FarmWorker, getFarm, setFarmAuto, startScenario } from "@/lib/api";
import { Rolling } from "@/lib/alive";

const STATE_WORD: Record<string, string> = {
  rendering: "rendering",
  idle: "idle",
  failed: "failed",
  blocked: "blocked",
  throttled: "throttled",
};

function WorkerCell({ w }: { w: FarmWorker }) {
  const job = w.job;
  return (
    <div
      className={`fw fw-${w.state}`}
      title={
        `${w.id} · ${w.pool} · ${STATE_WORD[w.state] ?? w.state}` +
        `\n${w.gpu}% GPU · ${w.temp_c}°C · ${w.vram_gb}GB card` +
        `\n${w.completed} done, ${w.failed} failed` +
        (w.note ? `\n${w.note}` : "") +
        (job ? `\njob ${job.id} · ${job.frames} frames · needs ${job.vram_gb}GB` : "")
      }
    >
      <div className="fw-top">
        <span className="fw-id">{w.id.replace("pool-", "")}</span>
        <span className="fw-temp">{Math.round(w.temp_c)}°</span>
      </div>

      {/* The bar is GPU load, so it is only drawn when the card is doing
          something. A blocked or idle worker gets an empty channel. */}
      <div className="fw-bar" aria-hidden="true">
        <i style={{ width: `${Math.max(0, Math.min(100, w.gpu))}%` }} />
      </div>

      <div className="fw-job">
        {job ? (
          <>
            <span className="fw-jid">{job.id}</span>
            <span className="fw-prog">{Math.round(job.progress * 100)}%</span>
          </>
        ) : (
          <span className="fw-none">{STATE_WORD[w.state] ?? w.state}</span>
        )}
      </div>
    </div>
  );
}

export function FarmFloor() {
  const [farm, setFarm] = useState<FarmView | null>(null);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = () =>
    getFarm()
      .then((f) => { setFarm(f); setError(""); })
      .catch((err) => setError(String(err)));

  useEffect(() => {
    load();
    timer.current = setInterval(load, 2000);
    return () => { if (timer.current) clearInterval(timer.current); };
  }, []);

  const fire = async (key: string) => {
    setPending(true);
    try { await startScenario(key); await load(); }
    catch (err) { setError(String(err)); }
    finally { setPending(false); }
  };

  if (error && !farm) {
    return (
      <div className="farm-down">
        <b>The render farm is not reachable.</b>
        <p>{error}</p>
        <p className="muted">
          Nothing is drawn here rather than showing an idle farm — an unreachable farm and a
          quiet one are different things.
        </p>
      </div>
    );
  }
  if (!farm) return <p className="muted">Reading the farm…</p>;

  const pools = [...new Set(farm.workers.map((w) => w.pool))];
  const busy = farm.workers.filter((w) => w.state === "rendering").length;

  return (
    <div className="farm-floor">
      <div className="farm-top">
        <div className="farm-stat">
          <b><Rolling value={busy} /><span className="of">/{farm.workers.length}</span></b>
          <span>rendering</span>
        </div>
        <div className="farm-stat">
          <b><Rolling value={farm.queued_total} /></b>
          <span>jobs waiting</span>
        </div>
        <div className="farm-stat">
          <b><Rolling value={Math.round(farm.gpu)} suffix="%" /></b>
          <span>mean GPU</span>
        </div>
        <div className="farm-stat">
          <b>{farm.latency_s.toFixed(1)}<i>s</i></b>
          <span>per render</span>
        </div>
        <div className={`farm-stat${farm.failed_total > 0 ? " bad" : ""}`}>
          <b><Rolling value={farm.failed_total} /></b>
          <span>failed</span>
        </div>
      </div>

      {farm.incident_label && (
        <p className="farm-incident">
          <span className="fi-dot" aria-hidden="true" />
          Running incident: <b>{farm.incident_label}</b>
        </p>
      )}

      {pools.map((pool) => (
        <div className="farm-pool" key={pool}>
          <div className="fp-head">
            {pool}
            <span className="muted">
              {" · "}{farm.workers.filter((w) => w.pool === pool && w.state === "rendering").length}
              {" of "}{farm.workers.filter((w) => w.pool === pool).length} rendering
            </span>
          </div>
          <div className="fp-grid">
            {farm.workers.filter((w) => w.pool === pool).map((w) => (
              <WorkerCell key={w.id} w={w} />
            ))}
          </div>
        </div>
      ))}

      <div className="farm-queue">
        <div className="fq-head">
          Queue <span className="muted">· {farm.queued_total} waiting</span>
        </div>
        <div className="fq-jobs">
          {farm.queued.length === 0 && <span className="muted">nothing waiting — the farm is keeping up</span>}
          {farm.queued.map((j) => (
            <span className="fq-job" key={j.id} title={`${j.frames} frames · needs ${j.vram_gb}GB`}>
              {j.id}
            </span>
          ))}
          {farm.queued_total > farm.queued.length && (
            <span className="fq-more">+{farm.queued_total - farm.queued.length} more</span>
          )}
        </div>
      </div>

      {farm.recent.length > 0 && (
        <div className="farm-recent">
          <div className="fq-head">Just finished</div>
          <ul>
            {farm.recent.map((j, i) => (
              <li key={`${j.id}-${i}`} className={j.state === "failed" ? "bad" : ""}>
                <span className="fr-id">{j.id}</span>
                <span className="fr-state">{j.state}</span>
                {j.note && <span className="fr-note">{j.note}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Demo controls. These change the world the agent observes — never its
          conclusions — and they are labelled as such so nobody watching mistakes
          a triggered fault for one the system found. */}
      <div className="farm-controls">
        <div className="fc-head">
          Break something <span className="muted">· this changes the farm, not the diagnosis</span>
        </div>
        <div className="fc-buttons">
          {farm.incidents.map((i) => (
            <button
              key={i.key}
              className={`fc-btn${farm.incident === i.key ? " on" : ""}`}
              onClick={() => fire(i.key)}
              disabled={pending}
              title={`${i.blurb}\n\nSignature: ${i.signature}`}
            >
              {i.label}
            </button>
          ))}
          <button className="fc-btn clear" onClick={() => fire("clear")}
                  disabled={pending || !farm.incident}>
            Clear
          </button>
          <button
            className={`fc-btn auto${farm.auto ? " on" : ""}`}
            onClick={async () => {
              setPending(true);
              try { await setFarmAuto(!farm.auto); await load(); }
              finally { setPending(false); }
            }}
            disabled={pending}
            title="Cycle through incidents unattended, so the loop keeps having something to find."
          >
            {farm.auto ? "Auto: on" : "Auto: off"}
          </button>
        </div>
        {error && <p className="fc-error">{error}</p>}
      </div>
    </div>
  );
}
