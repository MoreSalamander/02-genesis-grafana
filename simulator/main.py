"""Convergence Studios render-farm simulator.

Emits realistic render-pipeline telemetry for the Operational Intelligence
demo: Prometheus metrics on /metrics, error/info logs pushed to Loki, and a
control endpoint (/control/concurrency) that is the studio's actuation
boundary — reducing concurrency genuinely drains the queue, so post-action
verification through Grafana shows a real improvement.
"""
from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI
from prometheus_client import Counter, Gauge, make_asgi_app

LOKI_URL = os.getenv("LOKI_URL", "http://loki:3100")
TIME_SCALE = float(os.getenv("TIME_SCALE", "1.0"))  # >1 accelerates the scenario (demo pacing)

# --- Grafana Cloud push (optional; activates when configured) -------------
# Metrics go to the stack's Influx line-protocol endpoint (arrives in the
# hosted Prometheus as studio_<field> series); logs go to hosted Loki.
GC_PROM_PUSH_URL = os.getenv("GC_PROM_PUSH_URL", "")   # https://influx-prod-XX.grafana.net/api/v1/push/influx/write
GC_PROM_USER = os.getenv("GC_PROM_USER", "")            # numeric Prometheus instance id
GC_LOKI_PUSH_URL = os.getenv("GC_LOKI_PUSH_URL", "")    # https://logs-prod-XXX.grafana.net/loki/api/v1/push
GC_LOKI_USER = os.getenv("GC_LOKI_USER", "")            # numeric Loki instance id
GC_TOKEN = os.getenv("GC_TOKEN", "")                    # access-policy token (metrics:write + logs:write)

_ERRORS_CUM = 0.0  # cumulative counter mirrored to Grafana Cloud

GPU = Gauge("studio_gpu_utilization_percent", "GPU utilization of render Worker Pool A")
QUEUE = Gauge("studio_render_queue_depth", "Jobs waiting in the render queue")
LATENCY = Gauge("studio_render_latency_seconds", "Average render job latency")
ERRORS = Counter("studio_worker_errors_total", "Render worker errors")

app = FastAPI(title="Convergence Studios — Render Farm Simulator")
app.mount("/metrics", make_asgi_app())


class Scenario:
    """Heavy-scene incident: queue builds until concurrency is reduced."""

    def __init__(self):
        self.lock = threading.Lock()
        self.mode = "degrading"  # degrading | recovering | steady
        self.queue = 22.0
        self.gpu = 70.0
        self.latency = 3.1
        self.factor = 1.0

    def tick(self, dt_minutes: float) -> list[str]:
        logs: list[str] = []
        with self.lock:
            global _ERRORS_CUM
            if self.mode == "degrading":
                self.queue = min(120.0, self.queue + 2.0 * dt_minutes)
                self.gpu = min(96.0, 70.0 + self.queue * 0.30)
                self.latency = min(9.5, 3.0 + self.queue * 0.066)
                if self.gpu > 90:
                    ERRORS.inc(4.0 * dt_minutes)
                    _ERRORS_CUM += 4.0 * dt_minutes
                    logs = [
                        'level=error msg="CUDA out of memory" worker=pool-a job=shot-%04d' % (400 + int(self.queue)),
                        'level=error msg="render timeout after 480s" worker=pool-a job=shot-%04d' % (380 + int(self.queue)),
                        'level=error msg="job requeued: worker saturated" worker=pool-a job=shot-%04d' % (410 + int(self.queue)),
                    ]
            elif self.mode == "recovering":
                self.queue = max(30.0, self.queue - 3.2 * dt_minutes)
                self.gpu = max(74.0, self.gpu - 1.6 * dt_minutes)
                self.latency = max(4.5, self.latency - 0.28 * dt_minutes)
                if self.queue <= 40:
                    self.mode = "steady"
                logs = ['level=info msg="render job completed" worker=pool-b duration=4.6s']
            else:  # steady
                self.queue = max(28.0, min(45.0, self.queue))
                self.gpu = 76.0
                self.latency = 4.7
                logs = ['level=info msg="render job completed" worker=pool-a duration=4.4s']
            GPU.set(round(self.gpu, 2))
            QUEUE.set(round(self.queue, 2))
            LATENCY.set(round(self.latency, 3))
        return logs

    def set_concurrency(self, factor: float) -> dict:
        with self.lock:
            self.factor = factor
            if factor < 1.0:
                self.mode = "recovering"
            return self.snapshot()

    def degrade(self) -> dict:
        with self.lock:
            self.mode = "degrading"
            self.queue = max(self.queue, 22.0)
            return self.snapshot()

    def snapshot(self) -> dict:
        return {"mode": self.mode, "queue": round(self.queue, 1), "gpu": round(self.gpu, 1),
                "latency_s": round(self.latency, 2), "concurrency_factor": self.factor}


SCENARIO = Scenario()


def _push_logs(lines: list[str]) -> None:
    if not lines:
        return
    now_ns = str(int(datetime.now(timezone.utc).timestamp() * 1e9))
    level = "error" if "level=error" in lines[0] else "info"
    payload = {
        "streams": [{
            "stream": {"job": "render-worker", "service_name": "render-worker", "level": level},
            "values": [[now_ns, line] for line in lines],
        }]
    }
    try:
        httpx.post(f"{LOKI_URL}/loki/api/v1/push", json=payload, timeout=3.0)
    except Exception:
        pass  # local Loki optional — metrics remain authoritative
    if GC_LOKI_PUSH_URL and GC_TOKEN:
        try:
            httpx.post(GC_LOKI_PUSH_URL, json=payload, auth=(GC_LOKI_USER, GC_TOKEN), timeout=5.0)
        except Exception:
            pass


def _push_cloud_metrics() -> None:
    """Mirror current gauges to Grafana Cloud Prometheus via Influx line protocol."""
    if not (GC_PROM_PUSH_URL and GC_TOKEN):
        return
    snap = SCENARIO.snapshot()
    line = (
        "studio,job=render-farm-simulator "
        f"gpu_utilization_percent={snap['gpu']},"
        f"render_queue_depth={snap['queue']},"
        f"render_latency_seconds={snap['latency_s']},"
        f"worker_errors_total={round(_ERRORS_CUM, 2)}"
    )
    try:
        httpx.post(GC_PROM_PUSH_URL, content=line, auth=(GC_PROM_USER, GC_TOKEN),
                   headers={"content-type": "text/plain"}, timeout=5.0)
    except Exception:
        pass


def _loop() -> None:
    while True:
        logs = SCENARIO.tick(dt_minutes=(4 / 60) * TIME_SCALE)  # tick every 4s
        _push_logs(logs)
        _push_cloud_metrics()
        time.sleep(4)


threading.Thread(target=_loop, daemon=True).start()


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, **SCENARIO.snapshot()}


@app.post("/control/concurrency")
def control_concurrency(body: dict) -> dict:
    factor = max(0.5, min(1.0, float(body.get("factor", 0.8))))
    return SCENARIO.set_concurrency(factor)


@app.post("/scenario/degrade")
def scenario_degrade() -> dict:
    return SCENARIO.degrade()
