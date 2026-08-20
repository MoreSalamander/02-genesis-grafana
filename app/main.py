"""Genesis OS — Operational Intelligence — standalone service entry point.

Run:  uvicorn app.main:app --port 8010
Boots in MOCK mode with no configuration; LIVE mode activates when
GRAFANA_MCP_URL (official Grafana MCP server / Grafana Cloud MCP endpoint) and
Google credentials are present.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from app.api.routes import router
from app.workflows.run_investigation import get_runtime

app = FastAPI(
    title="Genesis OS — Operational Intelligence",
    description="Agentic operational cognition for Convergence Studios (Grafana track).",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3010", "http://127.0.0.1:3010"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.on_event("startup")
def announce() -> None:
    runtime = get_runtime()
    print(runtime.settings.banner())
    # The mission loop's trigger: firing alerts open investigations. Runs only
    # against a live MCP connection — mock mode exercises it in tests instead.
    if runtime.settings.alert_watch and runtime.settings.grafana_live:
        from app.agents.watch.alert_watch import WATCH

        WATCH.start(get_runtime, runtime.settings.alert_watch_interval_s)
        print(f"[alert-watch] watching for firing alerts every "
              f"{runtime.settings.alert_watch_interval_s:.0f}s")


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    runtime = get_runtime()
    return f"""<!doctype html><html><head><title>Genesis OS — Operational Intelligence</title>
<style>body{{font-family:ui-monospace,monospace;background:#0e1210;color:#d9e2dc;margin:3rem}}
a{{color:#4cc38a}} code{{color:#e5c07b}}</style></head><body>
<h1>GENESIS OS — OPERATIONAL INTELLIGENCE</h1>
<p>Operations · Convergence Studios · Grafana track</p>
<p><code>{runtime.settings.banner()}</code></p>
<ul>
<li><a href="/docs">API docs</a></li>
<li><code>POST /api/investigations</code> — "How is production doing right now?"</li>
<li><code>GET /api/investigations/&lt;id&gt;</code> — evidence, hypotheses, projection, incident card</li>
<li><code>POST /api/investigations/&lt;id&gt;/decision</code> — Studio Head authorization → act → verify</li>
</ul>
<p>Incident console: <code>frontend/</code> · Local Grafana stack: <code>ops/docker-compose.yml</code></p>
</body></html>"""


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8010, reload=False)
