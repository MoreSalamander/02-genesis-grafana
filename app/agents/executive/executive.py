"""Operational Executive (locked §3): owns the operational objective, delegates
to the cognitive hierarchy, and runs the full locked loop:

    OBSERVE → CORRELATE → DIAGNOSE → PREDICT → RECOMMEND → AUTHORIZE → ACT → VERIFY

Failure rules (§15): Grafana unavailable blocks the investigation (no fabricated
answer); successful action submission is never treated as successful outcome —
verification re-queries telemetry through Grafana and compares before/after.
"""
from __future__ import annotations

import time

from app.agents.correlation.correlator import CorrelationAgent
from app.agents.diagnosis.diagnostician import DiagnosisAgent
from app.agents.observability.analysts import AlertScanner, LogAnalyst, MetricsAnalyst, TraceAnalyst
from app.agents.prediction.predictor import PredictionAgent
from app.agents.remediation.planner import RemediationAgent
from app.config import Settings
from app.events.bus import EventBus
from app.governance.authority import record_decision
from app.knowledge.datahub import DataHubKnowledge
from app.memory.stores import EpisodicMemory
from app.models.operational import Investigation, InvestigationStatus, VerificationResult
from app.tools.grafana.mcp_client import GrafanaUnavailable
from app.tools.studio.control import StudioControl

CORE_SIGNALS = ("gpu_utilization_pct", "render_queue_depth", "render_latency_s")

# Where each evidence signal lives in Grafana — the deep links the track brief
# asks agents to hand back for human review. (dashboard uid, panel id)
_PANEL_FOR = {
    "gpu_utilization_pct": ("farm-floor", 4),
    "render_queue_depth": ("the-slate", 5),
    "render_latency_s": ("farm-floor", 7),
    "worker_error_rate_per_min": ("farm-floor", 6),
    "workers_rendering": ("farm-floor", 2),
    "gpu_temperature_c": ("farm-floor", 5),
}
_PANEL_FOR_KIND = {"log": ("the-slate", 6), "trace": ("farm-floor", 3), "alert": ("farm-floor", 1)}


class OperationalExecutive:
    name = "Operational Executive"
    permissions = ("read", "analyze", "recommend", "execute:approval-only")

    def __init__(
        self,
        settings: Settings,
        telemetry,
        control: StudioControl,
        correlator: CorrelationAgent,
        diagnostician: DiagnosisAgent,
        predictor: PredictionAgent,
        remediation: RemediationAgent,
        episodic: EpisodicMemory,
        bus: EventBus,
        knowledge: DataHubKnowledge,
    ):
        self.settings = settings
        self.telemetry = telemetry
        self.control = control
        self.knowledge = knowledge
        self.metrics = MetricsAnalyst()
        self.logs = LogAnalyst()
        self.traces = TraceAnalyst()
        self.alerts = AlertScanner()
        self.correlator = correlator
        self.diagnostician = diagnostician
        self.predictor = predictor
        self.remediation = remediation
        self.episodic = episodic
        self.bus = bus

    # ------------------------------------------------------------------ observe→recommend
    def recall(self, inv: Investigation) -> None:
        """Episodic recall before observation — the knowledge layer earning
        its keep. Retrieval is deterministic; the priors ride into diagnosis
        and planning where the prompts say it plainly: priors inform,
        evidence decides."""
        try:
            priors = self.episodic.similar(inv.question)
        except Exception:
            priors = []
        if not priors:
            return
        inv.recall = priors
        confirmed = [p for p in priors if p.get("improved")]
        top = priors[0]
        inv.stage("RECALL",
                  f"{len(priors)} similar past incident(s), {len(confirmed)} fixed and verified; "
                  f"strongest prior: {str(top.get('leading_cause'))[:90]}")
        self.bus.emit("memory.recalled", investigation_id=inv.id,
                      count=len(priors), confirmed=len(confirmed))
        self._annotate(inv, f"🧭 {inv.id} recalls {len(priors)} similar incident(s) — "
                            f"priors inform, evidence decides", "recall")

    def investigate(self, inv: Investigation) -> Investigation:
        inv.scope = self.knowledge.scope_for("render-worker")
        self.recall(inv)
        try:
            self._observe(inv)
            if not inv.anomalous_evidence:
                inv.status = InvestigationStatus.HEALTHY
                inv.stage("ALL CLEAR", "No anomalous operational signals in the window")
                self.bus.emit("investigation.completed", investigation_id=inv.id, outcome="healthy")
                self._finalize(inv)
                return inv
            self._correlate(inv)
            self._diagnose(inv)
            self._predict(inv)
            self._recommend(inv)
        except GrafanaUnavailable as err:
            self._incomplete(inv, f"Operational investigation blocked — Grafana MCP unavailable: {err}")
        except Exception as err:
            self._incomplete(inv, f"Agent failure: {err}")
        return inv

    def _observe(self, inv: Investigation) -> None:
        inv.status = InvestigationStatus.OBSERVING
        for analyst in (self.metrics, self.logs, self.traces):
            inv.evidence.extend(
                analyst.observe(self.telemetry, self.settings.thresholds, site=self.settings.site)
            )
        inv.evidence.extend(self.alerts.observe(self.telemetry))
        anomalies = inv.anomalous_evidence
        self.bus.emit("telemetry.observed", investigation_id=inv.id, evidence=len(inv.evidence),
                      anomalous=len(anomalies))
        for e in anomalies:
            self.bus.emit("anomaly.detected", investigation_id=inv.id, signal=e.name, detail=e.detail)
        inv.stage("OBSERVE", f"{len(inv.evidence)} telemetry evidence items via Grafana MCP, "
                             f"{len(anomalies)} anomalous")
        # Every piece of evidence links back to the Grafana panel it lives on —
        # "generate links back to Grafana for human review" is the brief's own
        # description of what a good agent does with its findings.
        base = self.settings.grafana_public_url
        for e in inv.evidence:
            uid_panel = _PANEL_FOR.get(e.name) or _PANEL_FOR_KIND.get(e.kind)
            if uid_panel and base:
                uid, panel = uid_panel
                e.link = (f"{base}/d/{uid}?viewPanel={panel}"
                          f"&from=now-{e.window_minutes}m&to=now&var-site={self.settings.site}")

    def _correlate(self, inv: Investigation) -> None:
        inv.status = InvestigationStatus.CORRELATING
        self.correlator.correlate(inv)
        chain = " → ".join(inv.correlation.chain) if inv.correlation and inv.correlation.chain else "none"
        inv.stage("CORRELATE", f"validated={bool(inv.correlation and inv.correlation.validated)} · {chain}")

    def _diagnose(self, inv: Investigation) -> None:
        inv.status = InvestigationStatus.DIAGNOSING
        self.diagnostician.diagnose(inv)
        leading = inv.leading_diagnosis
        inv.stage("DIAGNOSE", f"{len(inv.diagnoses)} competing hypotheses; leading: "
                              f"{leading.cause if leading else 'none'} "
                              f"({leading.confidence:.0%})" if leading else "no hypotheses")
        if leading:
            self._annotate(inv, f"🧠 {inv.id} root cause: {leading.cause} "
                                f"({leading.confidence:.0%} confidence)", "root-cause")

    def _predict(self, inv: Investigation) -> None:
        inv.status = InvestigationStatus.PREDICTING
        self.predictor.project(inv)
        if inv.projection:
            eta = f" in ~{inv.projection.eta_minutes:.0f} min" if inv.projection.eta_minutes else ""
            inv.stage("PREDICT", f"{inv.projection.event}{eta} · {inv.projection.at_risk}")

    def _recommend(self, inv: Investigation) -> None:
        self.remediation.plan(inv)
        inv.status = InvestigationStatus.AWAITING_AUTHORIZATION
        inv.stage("RECOMMEND", inv.plan.action if inv.plan else "")

    # ------------------------------------------------------------------ authorize→act→verify
    # Granular steps so the Temporal workflow can run each as a durable activity;
    # execute_decision remains the composed (non-workflow fallback) path.

    def decide(self, inv: Investigation, decision: str) -> None:
        record_decision(inv, decision, self.bus)
        action = inv.plan.action if inv.plan else ""
        self._annotate(inv, f"🪪 Studio Head {decision.upper()}: {action} — {inv.id}", f"decision-{decision}")

    def reject(self, inv: Investigation) -> Investigation:
        inv.status = InvestigationStatus.REJECTED
        self.bus.emit("investigation.completed", investigation_id=inv.id, outcome="rejected")
        self._finalize(inv)
        return inv

    def act(self, inv: Investigation) -> bool:
        inv.status = InvestigationStatus.ACTING
        # Fresh baseline at actuation time — the Studio Head may approve long after
        # observation, and verification must compare against reality at ACT, not at OBSERVE.
        inv.act_snapshot = self._live_snapshot() or self._snapshot(inv)
        ok, message = self.control.apply(inv.plan.actuation)
        self.bus.emit("remediation.executed", investigation_id=inv.id, ok=ok, detail=message)
        inv.stage("ACT", message)
        if ok:
            self._annotate(inv, f"🛠 Remediation applied: {message} — {inv.id}", "remediation-applied")
        if not ok:
            self._remediation_failed(inv, self._snapshot(inv), f"Actuation failed: {message}")
            return False
        return True

    def verify_outcome(self, inv: Investigation) -> Investigation:
        before = inv.act_snapshot or self._snapshot(inv)
        inv.status = InvestigationStatus.VERIFYING
        result = self._verify(inv, before)
        inv.verification = result
        if result.improved:
            inv.status = InvestigationStatus.REMEDIATED
            inv.stage("VERIFY", f"Remediation successful — {result.notes}")
            self.bus.emit("remediation.verified", investigation_id=inv.id, before=result.before,
                          after=result.after)
            self.bus.emit("investigation.completed", investigation_id=inv.id, outcome="remediated")
            self._annotate(inv, f"✅ Recovery confirmed — {result.notes} — {inv.id}", "recovery-confirmed")
            self._finalize(inv)
            return inv
        return self._remediation_failed(inv, before, result.notes, after=result.after)

    def execute_decision(self, inv: Investigation, decision: str) -> Investigation:
        self.decide(inv, decision)
        if decision == "rejected":
            return self.reject(inv)
        if not self.act(inv):
            return inv
        return self.verify_outcome(inv)

    def _snapshot(self, inv: Investigation) -> dict[str, float]:
        return {e.name: e.latest for e in inv.evidence if e.name in CORE_SIGNALS and e.latest is not None}

    def _live_snapshot(self) -> dict[str, float]:
        snapshot: dict[str, float] = {}
        try:
            for name, expr_template, *_ in MetricsAnalyst.METRICS:
                if name in CORE_SIGNALS:
                    data = self.telemetry.query_metric(
                        name, expr_template.format(site=self.settings.site), minutes=5
                    )
                    if data.get("latest") is not None:
                        snapshot[name] = data["latest"]
        except Exception:
            return {}
        return snapshot

    def _verify(self, inv: Investigation, before: dict[str, float]) -> VerificationResult:
        # 18 × 10s (live) so the window outlives the remediation's own capacity
        # dip: reducing concurrency clears the fault first and drains second.
        attempts = 18 if getattr(self.telemetry, "live", False) else 1
        delay = 10.0 if getattr(self.telemetry, "live", False) else 0.0
        history: list[dict[str, float]] = []
        after: dict[str, float] = {}
        for _ in range(attempts):
            if delay:
                time.sleep(delay)
            after = {}
            for name, expr_template, *_ in MetricsAnalyst.METRICS:
                if name in CORE_SIGNALS:
                    expr = expr_template.format(site=self.settings.site)
                    data = self.telemetry.query_metric(name, expr, minutes=5)
                    if data.get("latest") is not None:
                        after[name] = data["latest"]
            history.append(dict(after))
            if self._improved(before, after):
                return VerificationResult(
                    improved=True, before=before, after=after,
                    notes=", ".join(f"{k} {before.get(k)}→{after.get(k)}" for k in sorted(after)),
                )
            crest = self._crested(history, before)
            if crest:
                return VerificationResult(improved=True, before=before, after=after, notes=crest)
        return VerificationResult(
            improved=False, before=before, after=after,
            notes="Post-action telemetry did not improve within the verification window "
                  f"(action submission ≠ outcome){self._trajectory(history)}",
        )

    @staticmethod
    def _improved(before: dict[str, float], after: dict[str, float]) -> bool:
        gpu_ok = after.get("gpu_utilization_pct", 1e9) <= before.get("gpu_utilization_pct", 0) - 5
        queue_ok = after.get("render_queue_depth", 1e9) <= before.get("render_queue_depth", 0) - 10
        latency_ok = after.get("render_latency_s", 1e9) <= before.get("render_latency_s", 0) * 0.8
        return gpu_ok and (queue_ok or latency_ok)

    @staticmethod
    def _crested(history: list[dict[str, float]], before: dict[str, float]) -> str:
        """The trend bar. A backlog outlives the fault that built it, so a fix
        that worked shows up first as the queue CRESTING — a peak, then a
        strict drain — while GPU is no worse than when we acted (saturated
        workers eating a backlog are healthy, not sick). A verifier that
        cannot tell "draining" from "still broken" is a broken instrument,
        not a strict one. The absolute bar above still wins outright whenever
        the world is small enough to finish healing inside the window.
        Returns the honest basis for the pass, or "" when the trend does not
        support one."""
        qs = [h["render_queue_depth"] for h in history if "render_queue_depth" in h]
        if len(qs) < 6:
            return ""
        peak = max(qs)
        recent = sum(qs[-3:]) / 3
        prior = sum(qs[-6:-3]) / 3
        if not (recent <= peak - max(5.0, 0.02 * peak) and recent < prior):
            return ""
        gpu_now = history[-1].get("gpu_utilization_pct")
        gpu_before = before.get("gpu_utilization_pct")
        if gpu_now is not None and gpu_before is not None and gpu_now > gpu_before + 2:
            return ""
        rate = (prior - recent) * 2  # sample means sit ~30s apart → jobs/min
        gpu_bit = (f"; gpu {gpu_before:.0f}→{gpu_now:.0f}"
                   if gpu_now is not None and gpu_before is not None else "")
        return (f"queue crested at {peak:.0f} and is draining — now {qs[-1]:.0f} "
                f"(≈{rate:.1f} jobs/min){gpu_bit}; verified on trend reversal: "
                "the backlog outlives the fault, and the bleeding has stopped")

    @staticmethod
    def _trajectory(history: list[dict[str, float]]) -> str:
        """Failure forensics: what the queue actually did across the window."""
        qs = [h["render_queue_depth"] for h in history if "render_queue_depth" in h]
        if len(qs) < 2:
            return ""
        word = "still climbing" if qs[-1] >= max(qs) else "cresting, drain not yet confirmed"
        return f"; queue {qs[0]:.0f}→{qs[-1]:.0f} over the window ({word})"

    def _remediation_failed(self, inv: Investigation, before: dict, notes: str, after: dict | None = None):
        inv.status = InvestigationStatus.REMEDIATION_FAILED
        inv.escalated = True
        inv.escalation_reason = notes
        inv.verification = inv.verification or VerificationResult(improved=False, before=before,
                                                                  after=after or {}, notes=notes)
        inv.stage("VERIFY", f"FAILED — {notes}")
        self.bus.emit("remediation.failed", investigation_id=inv.id, reason=notes)
        self.bus.emit("escalation.raised", investigation_id=inv.id, reason=notes)
        self._annotate(inv, f"⛔ Remediation FAILED — {notes} — {inv.id}", "remediation-failed")
        self._finalize(inv)
        return inv

    def _annotate(self, inv: Investigation, text: str, tag: str) -> None:
        """The agent's mark on the dashboards. Meta-telemetry: a failed
        annotation never breaks the loop it is describing."""
        try:
            fn = getattr(self.telemetry, "create_annotation", None)
            if fn is not None:
                fn(text=text, tags=["genesis", inv.id, tag])
                inv.annotations_written.append(tag)
        except Exception:
            pass

    def _finalize(self, inv: Investigation) -> None:
        """Episodic memory + DataHub provenance + latch release on completion."""
        # Close the IRM loop when an incident rode along with the trigger.
        incident_id = (inv.trigger or {}).get("incident_id", "")
        if incident_id:
            try:
                self.telemetry.add_incident_activity(
                    incident_id,
                    f"{inv.id} finished: {inv.status.value}. "
                    + (f"Root cause: {inv.leading_diagnosis.cause}. " if inv.leading_diagnosis else "")
                    + (inv.verification.notes if inv.verification else ""),
                )
            except Exception:
                pass
        # Clip the play BEFORE the episodic write: records are judged against
        # the career as it stood when the play was made.
        try:
            from app import plays

            episodes_before = self.episodic.list(limit=500)
            play = plays.capture(inv, episodes_before)
            if play:
                self._annotate(inv, f"🎬 Play saved: {play['title']} — {inv.id}", "play-saved")
        except Exception:
            pass
        self.episodic.record(inv)
        if self.knowledge.emit_investigation(inv):
            inv.stage("PROVENANCE", "Investigation recorded in DataHub with lineage to render-worker")
        ephemeral = getattr(self, "ephemeral", None)
        if ephemeral is not None:
            from app.memory.ephemeral import INVESTIGATION_LATCH

            ephemeral.release_latch(INVESTIGATION_LATCH)

    def _incomplete(self, inv: Investigation, reason: str) -> None:
        inv.status = InvestigationStatus.INCOMPLETE
        inv.error = reason
        inv.stage("INCOMPLETE", reason)
        self.bus.emit("investigation.incomplete", investigation_id=inv.id, reason=reason)
        self._finalize(inv)
