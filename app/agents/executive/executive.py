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
    def investigate(self, inv: Investigation) -> Investigation:
        inv.scope = self.knowledge.scope_for("render-worker")
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
        attempts = 10 if getattr(self.telemetry, "live", False) else 1
        delay = 6.0 if getattr(self.telemetry, "live", False) else 0.0
        after: dict[str, float] = {}
        for attempt in range(attempts):
            if delay:
                time.sleep(delay)
            after = {}
            for name, expr_template, *_ in MetricsAnalyst.METRICS:
                if name in CORE_SIGNALS:
                    expr = expr_template.format(site=self.settings.site)
                    data = self.telemetry.query_metric(name, expr, minutes=5)
                    if data.get("latest") is not None:
                        after[name] = data["latest"]
            if self._improved(before, after):
                return VerificationResult(
                    improved=True, before=before, after=after,
                    notes=", ".join(f"{k} {before.get(k)}→{after.get(k)}" for k in sorted(after)),
                )
        return VerificationResult(
            improved=False, before=before, after=after,
            notes="Post-action telemetry did not improve within the verification window "
                  "(action submission ≠ outcome)",
        )

    @staticmethod
    def _improved(before: dict[str, float], after: dict[str, float]) -> bool:
        gpu_ok = after.get("gpu_utilization_pct", 1e9) <= before.get("gpu_utilization_pct", 0) - 5
        queue_ok = after.get("render_queue_depth", 1e9) <= before.get("render_queue_depth", 0) - 10
        latency_ok = after.get("render_latency_s", 1e9) <= before.get("render_latency_s", 0) * 0.8
        return gpu_ok and (queue_ok or latency_ok)

    def _remediation_failed(self, inv: Investigation, before: dict, notes: str, after: dict | None = None):
        inv.status = InvestigationStatus.REMEDIATION_FAILED
        inv.escalated = True
        inv.escalation_reason = notes
        inv.verification = inv.verification or VerificationResult(improved=False, before=before,
                                                                  after=after or {}, notes=notes)
        inv.stage("VERIFY", f"FAILED — {notes}")
        self.bus.emit("remediation.failed", investigation_id=inv.id, reason=notes)
        self.bus.emit("escalation.raised", investigation_id=inv.id, reason=notes)
        self._finalize(inv)
        return inv

    def _finalize(self, inv: Investigation) -> None:
        """Episodic memory + DataHub provenance + latch release on completion."""
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
