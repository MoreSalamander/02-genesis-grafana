"""Grafana MCP integration — the operational telemetry substrate (locked §5).

LIVE mode connects to the official Grafana MCP server (`mcp/grafana` container
or the hosted Grafana Cloud MCP endpoint) over streamable-HTTP via the MCP
Python SDK, and calls its tools at runtime: `list_datasources`,
`query_prometheus`, `query_loki_logs`, `list_alert_rules` — satisfying the
Grafana-track requirement that the stack is actively used through MCP.

MOCK mode serves a deterministic render-pipeline degradation scenario so the
full OBSERVE→…→VERIFY loop runs from a clean clone. Statistics (latest, average,
slope) are always computed here in code — cognition never invents telemetry
(locked §14).
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from app.config import Settings
from app import runtime_proof


class GrafanaUnavailable(RuntimeError):
    """Raised when the MCP server cannot be reached / a tool call fails (locked §15:
    investigation is blocked and escalated — never answered with fabricated data)."""


def series_stats(samples: list[tuple[float, float]]) -> dict:
    if not samples:
        return {"latest": None, "average": None, "slope_per_min": None}
    values = [v for _, v in samples]
    latest = values[-1]
    average = sum(values) / len(values)
    if len(samples) >= 2:
        t0, v0 = samples[0]
        t1, v1 = samples[-1]
        minutes = max((t1 - t0) / 60.0, 1e-6)
        slope = (v1 - v0) / minutes
    else:
        slope = 0.0
    return {"latest": round(latest, 2), "average": round(average, 2), "slope_per_min": round(slope, 3)}


# ---------------------------------------------------------------------------
# LIVE — official Grafana MCP server via the MCP Python SDK
# ---------------------------------------------------------------------------

class LiveGrafanaMCP:
    live = True

    def __init__(self, settings: Settings):
        self.settings = settings
        self.url = settings.grafana_mcp_url
        self.headers = (
            {"Authorization": f"Bearer {settings.grafana_mcp_token}"} if settings.grafana_mcp_token else None
        )
        self._prom_uid = settings.prometheus_uid
        self._loki_uid = settings.loki_uid

    # -- MCP plumbing -------------------------------------------------------
    def _call(self, tool: str, args: dict) -> Any:
        from app.observability.tracing import span as otel_span

        # Every MCP tool goes through here, so this is where the runtime proof
        # belongs: a configured URL is not evidence, a returned call is. Until
        # one lands, /status reports the partner as IDLE rather than LIVE.
        with otel_span(f"grafana.mcp.{tool}", tool=tool):
            try:
                result = self._call_inner(tool, args)
            except Exception as err:
                runtime_proof.record("grafana", "DEGRADED",
                                     f"MCP call '{tool}' failed against {self.url} ({err})")
                raise
            runtime_proof.record("grafana", "LIVE",
                                 f"MCP tool '{tool}' returned from {self.url}")
            return result

    def _call_inner(self, tool: str, args: dict) -> Any:
        async def run():
            from mcp import ClientSession

            try:  # mcp SDK ≥ 1.x late / 2.x: streams tuple + headers via custom http client
                from mcp.client.streamable_http import streamable_http_client as connect

                kwargs: dict = {}
                if self.headers:
                    try:
                        import httpx2 as _httpx  # SDK's bundled httpx fork, when present
                    except ImportError:
                        import httpx as _httpx
                    kwargs["http_client"] = _httpx.AsyncClient(headers=self.headers)
                async with connect(self.url, **kwargs) as streams:
                    read, write = streams[0], streams[1]
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        return await session.call_tool(tool, args)
            except ImportError:  # older SDK spelling
                from mcp.client.streamable_http import streamablehttp_client as connect_old

                async with connect_old(self.url, headers=self.headers) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        return await session.call_tool(tool, args)

        last_err: Exception | None = None
        for attempt in range(2):
            try:
                result = asyncio.run(run())
                if getattr(result, "isError", False):
                    raise RuntimeError(f"MCP tool {tool} returned error: {_payload(result)}")
                return _payload(result)
            except Exception as err:
                last_err = err
                time.sleep(1.0 + attempt)
        raise GrafanaUnavailable(f"Grafana MCP call '{tool}' failed: {last_err}")

    def _datasource_uid(self, ds_type: str) -> str:
        cached = self._prom_uid if ds_type == "prometheus" else self._loki_uid
        if cached:
            return cached
        payload = self._call("list_datasources", {})
        items = payload if isinstance(payload, list) else payload.get("datasources", payload.get("items", []))
        candidates = [i for i in (items or []) if str(i.get("type", "")).lower() == ds_type]
        if not candidates:
            raise GrafanaUnavailable(f"No {ds_type} datasource visible through Grafana MCP")

        # Grafana Cloud stacks ship several datasources per type (usage insights,
        # ML metrics, alert-state-history…). Prefer the primary telemetry one.
        def rank(item: dict) -> tuple:
            ident = (str(item.get("uid", "")) + " " + str(item.get("name", ""))).lower()
            primary = "grafanacloud-logs" in ident if ds_type == "loki" else "grafanacloud-prom" in ident
            secondary = not any(word in ident for word in ("alert-state", "usage", "ml-", "-ml", "insights"))
            return (primary, item.get("isDefault", False), secondary)

        uid = max(candidates, key=rank).get("uid", "")
        if ds_type == "prometheus":
            self._prom_uid = uid
        else:
            self._loki_uid = uid
        return uid

    # -- telemetry interface --------------------------------------------------
    def query_metric(self, name: str, expr: str, minutes: int = 30) -> dict:
        # NOTE: the server's time parser accepts relative expressions ('now-30m') or
        # RFC3339 WITHOUT fractional seconds — relative is the robust choice.
        payload = self._call(
            "query_prometheus",
            {
                "datasourceUid": self._datasource_uid("prometheus"),
                "expr": expr,
                "startTime": f"now-{minutes}m",
                "endTime": "now",
                "queryType": "range",
                "stepSeconds": 30,
            },
        )
        samples = _extract_series(payload)
        return {"query": expr, "samples": samples, **series_stats(samples)}

    def query_logs(self, logql: str, minutes: int = 30, limit: int = 40) -> dict:
        payload = self._call(
            "query_loki_logs",
            {
                "datasourceUid": self._datasource_uid("loki"),
                "logql": logql,
                "limit": limit,
                "startRfc3339": f"now-{minutes}m",
                "endRfc3339": "now",
            },
        )
        lines = _extract_log_lines(payload)
        return {"query": logql, "lines": lines, "count": len(lines)}

    def list_alerts(self) -> list[str]:
        # Prefer list_alert_rules (Grafana-managed alerting API — fast everywhere);
        # list_alert_groups is the fallback (on Grafana Cloud it routes to OnCall,
        # which is slow/absent on stacks without IRM provisioned).
        payload = None
        for tool in ("list_alert_rules", "list_alert_groups"):
            try:
                payload = self._call(tool, {})
                break
            except GrafanaUnavailable:
                continue
        if payload is None:
            return []
        items = payload if isinstance(payload, list) else payload.get(
            "items", payload.get("rules", payload.get("groups", []))
        )
        alerts = []
        for item in items or []:
            if not isinstance(item, dict):
                continue
            title = item.get("title", item.get("name", item.get("labels", {}).get("alertname", "alert")))
            state = item.get("state", item.get("status", {}).get("state", "unknown")) \
                if isinstance(item.get("status", {}), dict) else item.get("state", "unknown")
            alerts.append(f"{title}: {state}")
        return alerts


def _payload(result: Any) -> Any:
    structured = getattr(result, "structuredContent", None)
    if structured:
        return structured
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            try:
                return json.loads(text)
            except (json.JSONDecodeError, TypeError):
                return {"text": text}
    return {}


def _extract_series(payload: Any) -> list[tuple[float, float]]:
    """Handle mcp-grafana list-shaped, Prometheus-API-shaped, and frame-shaped results."""
    if isinstance(payload, dict):
        data = payload.get("data", payload)
        # mcp-grafana (observed live): {"data": [{"metric": {...}, "values": [[ts, "v"], ...]}]}
        if isinstance(data, list) and data and isinstance(data[0], dict) and "values" in data[0]:
            try:
                return [(float(ts), float(v)) for ts, v in data[0]["values"]]
            except (TypeError, ValueError):
                return []
        result = data.get("result") if isinstance(data, dict) else None
        if isinstance(result, list) and result:
            values = result[0].get("values") or ([result[0].get("value")] if result[0].get("value") else [])
            return [(float(ts), float(v)) for ts, v in values]
        frames = payload.get("frames") or (data.get("frames") if isinstance(data, dict) else None)
        if isinstance(frames, list) and frames:
            vals = frames[0].get("data", {}).get("values", [])
            if len(vals) >= 2:
                times, series = vals[0], vals[1]
                return [(float(t) / (1000.0 if float(t) > 1e12 else 1.0), float(v))
                        for t, v in zip(times, series) if v is not None]
    if isinstance(payload, list):  # some versions return the result list directly
        try:
            return [(float(ts), float(v)) for ts, v in payload]
        except (TypeError, ValueError):
            pass
    return []


def _extract_log_lines(payload: Any) -> list[str]:
    lines: list[str] = []
    # mcp-grafana (observed live): {"data": [{"line": "...", "labels": {...}}, ...]}
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        extracted = [str(item["line"]) for item in payload["data"]
                     if isinstance(item, dict) and "line" in item]
        if extracted:
            return extracted
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, str):
                lines.append(item)
            elif isinstance(item, dict):
                lines.append(str(item.get("line", item.get("message", item))))
    elif isinstance(payload, dict):
        for stream in payload.get("streams", []) or []:
            for _, line in stream.get("values", []) or []:
                lines.append(line)
        if not lines and payload.get("text"):
            lines = str(payload["text"]).splitlines()
    return lines


# ---------------------------------------------------------------------------
# MOCK — deterministic render-pipeline degradation scenario
# ---------------------------------------------------------------------------

class MockOpsState:
    """Shared scenario state so telemetry and actuation cohere in mock mode."""

    def __init__(self):
        self.remediated = False
        self.allow_improvement = True  # tests can force a failed remediation


_MOCK_STATE = MockOpsState()


def mock_state() -> MockOpsState:
    return _MOCK_STATE


def _ramp(start: float, end: float, points: int) -> list[float]:
    return [start + (end - start) * i / (points - 1) for i in range(points)]


class MockGrafanaTelemetry:
    live = False

    _DEGRADED = {
        "gpu_utilization_pct": (70, 94),
        "render_queue_depth": (22, 81),
        "render_latency_s": (3.1, 8.4),
        "worker_error_rate_per_min": (0.2, 4.2),
    }
    _RECOVERED = {
        "gpu_utilization_pct": (94, 76),
        "render_queue_depth": (81, 39),
        "render_latency_s": (8.4, 4.7),
        "worker_error_rate_per_min": (4.2, 0.4),
    }

    def __init__(self, state: MockOpsState | None = None):
        self.state = state or _MOCK_STATE

    def _series(self, metric: str, minutes: int) -> list[tuple[float, float]]:
        table = self._RECOVERED if (self.state.remediated and self.state.allow_improvement) else self._DEGRADED
        start, end = table.get(metric, (1.0, 1.0))
        points = max(minutes, 10)
        now = time.time()
        values = _ramp(start, end, points)
        return [(now - 60 * (points - 1 - i), round(v, 2)) for i, v in enumerate(values)]

    def query_metric(self, name: str, expr: str, minutes: int = 30) -> dict:
        samples = self._series(name, minutes)
        return {"query": expr, "samples": samples, **series_stats(samples)}

    def query_logs(self, logql: str, minutes: int = 30, limit: int = 40) -> dict:
        if self.state.remediated and self.state.allow_improvement:
            lines = ['level=info msg="render job completed" worker=pool-a duration=4.4s']
        else:
            lines = [
                'level=error msg="CUDA out of memory" worker=pool-a job=shot-0447',
                'level=error msg="render timeout after 480s" worker=pool-a job=shot-0431',
                'level=error msg="job requeued: worker saturated" worker=pool-a job=shot-0452',
                'level=error msg="CUDA out of memory" worker=pool-a job=shot-0455',
                'level=error msg="render timeout after 480s" worker=pool-a job=shot-0439',
                'level=error msg="job requeued: worker saturated" worker=pool-a job=shot-0461',
                'level=error msg="CUDA out of memory" worker=pool-a job=shot-0463',
                'level=error msg="render timeout after 480s" worker=pool-a job=shot-0470',
                'level=error msg="job requeued: worker saturated" worker=pool-a job=shot-0472',
            ]
        return {"query": logql, "lines": lines[:limit], "count": len(lines)}

    def list_alerts(self) -> list[str]:
        if self.state.remediated and self.state.allow_improvement:
            return ["RenderQueueDepthHigh: normal", "WorkerErrorBurst: normal"]
        return ["RenderQueueDepthHigh: firing", "WorkerErrorBurst: firing"]


def get_telemetry(settings: Settings):
    if settings.grafana_live:
        return LiveGrafanaMCP(settings)
    return MockGrafanaTelemetry()
