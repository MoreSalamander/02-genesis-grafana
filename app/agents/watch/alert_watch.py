"""The alert watch — the mission loop's trigger (Phase C).

The track brief's canonical mission begins with "investigate a firing alert",
so investigations here begin where a studio's actually do: an alert fires in
Grafana, and the system opens the investigation itself. The watch polls the
Grafana alertmanager through the MCP server (the same connection the track
checks), dedupes by alert fingerprint with a cooldown, honors the one-active
investigation latch, and — when IRM is available — opens a Grafana Incident
that the loop reports back into.

Autonomous cognition, zero autonomous authority: the watch may open an
investigation, but remediation still stops at the Studio Head's approval,
exactly as the locked human boundary (§10) demands.
"""
from __future__ import annotations

import threading
import time

from app.models.operational import Investigation


class AlertWatch:
    # A fingerprint is not re-investigated until this many seconds pass —
    # alerts stay firing for the whole time a fault exists, and one fault is
    # one investigation, not one per poll.
    COOLDOWN_S = 20 * 60

    def __init__(self):
        self._seen: dict[str, float] = {}
        self._thread: threading.Thread | None = None

    # -- one poll, testable in isolation ------------------------------------
    def poll_once(self, runtime) -> Investigation | None:
        from app.memory.ephemeral import INVESTIGATION_LATCH, LATCH_TTL_S
        from app.workflows.run_investigation import dispatch_investigation, run_investigation

        telemetry = runtime.executive.telemetry
        firing = telemetry.firing_alerts()
        now = time.time()
        for alert in firing:
            fp = alert.get("fingerprint", "")
            if not fp or now - self._seen.get(fp, 0) < self.COOLDOWN_S:
                continue
            labels = alert.get("labels", {})
            # Only the studio's own rules open investigations — every rule we
            # provision carries a domain label. Foreign alerts are somebody
            # else's story.
            if "domain" not in labels:
                self._seen[fp] = now
                continue
            # Two farms share one Grafana stack (local and hosted, split by the
            # site label). Each agent answers only for its own site — a foreign
            # site's alert belongs to that site's watcher, so it is skipped
            # without being marked seen.
            alert_site = labels.get("site", "")
            if alert_site and alert_site != runtime.settings.site:
                continue

            question = self._question(alert)
            inv = Investigation(question=question)
            holder = runtime.ephemeral.acquire_latch(INVESTIGATION_LATCH, inv.id, LATCH_TTL_S)
            if holder is not None:
                return None  # one operational reality at a time — retry next poll
            self._seen[fp] = now
            inv.trigger = {
                "source": "grafana-alert",
                "alertname": alert.get("alertname", ""),
                "labels": labels,
                "fingerprint": fp,
                "summary": alert.get("summary", ""),
                "starts_at": alert.get("starts_at", ""),
            }
            # The stretch beat: a real Grafana IRM incident, when the stack
            # offers one. '' means it doesn't, and the loop carries on.
            if runtime.settings.irm_incidents:
                severity = "critical" if labels.get("severity") == "critical" else "major"
                incident_id = getattr(telemetry, "create_incident", lambda **_: "")(
                    title=question[:120], severity=severity,
                )
                if incident_id:
                    inv.trigger["incident_id"] = incident_id
            runtime.working.put(inv)
            runtime.bus.emit("alert.triggered", investigation_id=inv.id,
                             alertname=inv.trigger["alertname"], fingerprint=fp)
            inv.stage("TRIGGER", f"Opened from firing alert '{inv.trigger['alertname']}' "
                                 f"({labels.get('title', labels.get('domain', ''))})")
            runtime.working.put(inv)
            try:
                telemetry.create_annotation(
                    text=f"🔎 {inv.id} opened from firing alert "
                         f"'{inv.trigger['alertname']}' — {alert.get('summary', '')[:160]}",
                    tags=["genesis", inv.id, "investigation-opened"],
                )
                inv.annotations_written.append("investigation-opened")
                runtime.working.put(inv)
            except Exception:
                pass  # the mark is meta-telemetry; the investigation is the point
            execution = dispatch_investigation(inv.id)
            if execution == "local":
                threading.Thread(target=run_investigation, args=(inv.id,), daemon=True).start()
            return inv
        return None

    @staticmethod
    def _question(alert: dict) -> str:
        labels = alert.get("labels", {})
        name = alert.get("alertname", "alert")
        subject = labels.get("title", "")
        summary = alert.get("summary", "")
        if subject:
            return f"ALERT {name}: {subject} — {summary}"[:300] if summary else \
                   f"ALERT {name}: {subject} — find the cause and recommend an action"[:300]
        return f"ALERT {name}: {summary}"[:300] if summary else \
               f"ALERT {name} is firing — find the cause and recommend an action"[:300]

    # -- the background loop -------------------------------------------------
    def start(self, get_runtime, interval_s: float) -> None:
        if self._thread is not None:
            return

        def loop() -> None:
            while True:
                try:
                    self.poll_once(get_runtime())
                except Exception as err:  # the watch must outlive any single failure
                    print(f"[alert-watch] poll error: {err}", flush=True)
                time.sleep(interval_s)

        self._thread = threading.Thread(target=loop, daemon=True, name="alert-watch")
        self._thread.start()


WATCH = AlertWatch()
