"""Gemini cognition for Operational Intelligence (locked §14): investigation
interpretation, hypothesis generation/comparison, causal reasoning, risk
narrative, remediation planning. It never invents telemetry — every payload it
sees was retrieved through Grafana MCP, and all numeric statistics are computed
in code before cognition runs.

LIVE = official `google-genai` SDK (accepted hackathon SDK, called at runtime).
MOCK = deterministic stand-in so a clean clone runs with no credentials.
"""
from __future__ import annotations

import json
import re
from typing import Any, Protocol

from app.config import Settings
from app import runtime_proof

ROLE_PROMPTS: dict[str, str] = {
    "correlation_hypothesis": (
        "You are the Correlation cognition of a film studio's operational intelligence system. "
        "Given anomalous and normal telemetry signals (name, latest, slope, anomalous), decide whether "
        "they are causally related and, if so, propose ONE causal chain. Return JSON: "
        "{\"related\": bool, \"chain\": [str, ...], \"rationale\": str}. Ground every element in the "
        "provided signals; do not invent signals."
    ),
    "diagnosis": (
        "You are the Incident Diagnosis cognition. Given telemetry signals (with ids) and a log summary, "
        "produce 2-4 COMPETING root-cause hypotheses. Return JSON: {\"hypotheses\": [{\"cause\": str, "
        "\"confidence\": float 0-1, \"supporting_ids\": [str], \"contradicting_ids\": [str], "
        "\"contradiction_notes\": str, \"severity\": \"LOW|MEDIUM|HIGH|CRITICAL\", \"affected\": str}]}. "
        "Confidences must reflect evidence coverage; preserve genuine contradictions rather than resolving them."
    ),
    "risk_projection": (
        "You are the Risk/Prediction cognition. You are given computed trend facts (current value, slope per "
        "minute, capacity threshold, computed eta_minutes). Write the projection. Return JSON: {\"event\": str, "
        "\"at_risk\": str, \"basis\": str}. Use ONLY the provided numbers; do not recompute or invent."
    ),
    "remediation_plan": (
        "You are the Remediation Planning cognition for a render pipeline. Given the leading diagnosis and "
        "signals, propose ONE bounded, reversible operational action the Studio Head can authorize. Return "
        "JSON: {\"action\": str, \"expected_effects\": [str], \"risk\": \"LOW|MEDIUM|HIGH\", "
        "\"actuation\": {\"type\": \"concurrency\", \"factor\": float 0-1}}. Diagnosis does not equal "
        "execution: the plan requires human authorization."
    ),
}


class Cognition(Protocol):
    live: bool

    def generate_json(self, role: str, payload: dict[str, Any]) -> dict[str, Any]: ...


# Flash-tier list prices per token (USD), for the gen_ai.usage.cost estimate.
_IN_RATE = 0.075 / 1_000_000
_OUT_RATE = 0.30 / 1_000_000


class GeminiCognition:
    live = True

    def __init__(self, settings: Settings):
        from google import genai  # accepted hackathon SDK: google-genai

        self._client = genai.Client()
        self._model = settings.gemini_model

    def generate_json(self, role: str, payload: dict[str, Any]) -> dict[str, Any]:
        import time

        from app import cognition_ledger
        from app.observability.tracing import span

        prompt = ROLE_PROMPTS[role] + "\n\nINPUT:\n" + json.dumps(payload, ensure_ascii=False)
        started = time.monotonic()
        tokens: dict[str, int] = {}
        try:
            with span("gemini.generate", role=role, model=self._model) as sp:
                response = self._client.models.generate_content(
                    model=self._model,
                    contents=prompt,
                    config={"response_mime_type": "application/json", "temperature": 0.2},
                )
                usage = getattr(response, "usage_metadata", None)
                if usage is not None:
                    tokens = {
                        "prompt": getattr(usage, "prompt_token_count", 0) or 0,
                        "total": getattr(usage, "total_token_count", 0) or 0,
                    }
                if sp is not None and tokens:
                    sp.set_attribute("tokens.prompt", tokens["prompt"])
                    sp.set_attribute("tokens.total", tokens["total"])
                    # gen_ai semantic conventions, set by our own hand — the
                    # SDK auto-instrumentors don't hook this call path, and
                    # first-party attributes are the more honest record anyway.
                    # Cost is an estimate from list prices, and says so.
                    out_tokens = max(0, tokens["total"] - tokens["prompt"])
                    sp.set_attribute("gen_ai.system", "gemini")
                    sp.set_attribute("gen_ai.operation.name", "chat")
                    sp.set_attribute("gen_ai.request.model", self._model)
                    sp.set_attribute("gen_ai.usage.input_tokens", tokens["prompt"])
                    sp.set_attribute("gen_ai.usage.output_tokens", out_tokens)
                    sp.set_attribute("gen_ai.usage.total_tokens", tokens["total"])
                    sp.set_attribute("gen_ai.usage.cost", round(
                        tokens["prompt"] * _IN_RATE + out_tokens * _OUT_RATE, 8))
                    sp.set_attribute("gen_ai.usage.cost.basis", "list-price estimate")
        except Exception as err:
            # A failed call is part of the reasoning record. Dropping it would
            # leave the console showing an unbroken run of successes.
            cognition_ledger.record(
                role=role, model=self._model, live=True, prompt=prompt, raw="",
                ms=int((time.monotonic() - started) * 1000), parsed_ok=False,
                tokens=tokens, error=f"{type(err).__name__}: {err}",
            )
            raise
        # First-hand proof of Google Cloud usage: the call came back.
        runtime_proof.record("gemini", "LIVE",
                             f"{self._model} returned a response this session")
        text = response.text or ""
        ms = int((time.monotonic() - started) * 1000)

        # Record the exact prompt and the exact reply, before parsing. The
        # console renders the reasoning from this, so it has to be what was
        # really sent and really returned — not a retelling of the parsed result.
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                parsed = json.loads(match.group(0))
            else:
                cognition_ledger.record(
                    role=role, model=self._model, live=True, prompt=prompt, raw=text,
                    ms=ms, parsed_ok=False, tokens=tokens,
                    error="response was not JSON and contained no JSON object",
                )
                raise
        cognition_ledger.record(
            role=role, model=self._model, live=True, prompt=prompt, raw=text,
            ms=ms, parsed_ok=True, tokens=tokens,
        )
        return parsed


class MockCognition:
    live = False

    def generate_json(self, role: str, payload: dict[str, Any]) -> dict[str, Any]:
        import time

        from app import cognition_ledger

        handler = getattr(self, f"_{role}", None)
        if handler is None:
            raise ValueError(f"MockCognition has no handler for role '{role}'")
        started = time.monotonic()
        result = handler(payload)
        # Recorded too, and flagged live=False. The reasoning panel is honest
        # about this: these are deterministic fixtures, and it says so rather
        # than showing rule output under a model's name.
        cognition_ledger.record(
            role=role, model="fixture (no model called)", live=False,
            prompt=ROLE_PROMPTS.get(role, "") + "\n\nINPUT:\n"
                   + json.dumps(payload, ensure_ascii=False, default=str),
            raw=json.dumps(result, ensure_ascii=False, default=str),
            ms=int((time.monotonic() - started) * 1000), parsed_ok=True,
        )
        return result

    def _correlation_hypothesis(self, payload: dict) -> dict:
        anomalous = [s for s in payload.get("signals", []) if s.get("anomalous")]
        if len(anomalous) < 3:
            return {"related": False, "chain": [], "rationale": "Fewer than three anomalous signals; no correlation formed."}
        return {
            "related": True,
            "chain": [
                "Worker resource saturation (GPU utilization climbing)",
                "Render latency increase",
                "Queue accumulation",
                "Job timeouts",
                "Worker errors",
            ],
            "rationale": "GPU utilization, render latency, queue depth and worker errors rose together over the window; "
                         "the propagation order matches resource saturation.",
        }

    def _diagnosis(self, payload: dict) -> dict:
        by_name = {s.get("name"): s.get("id") for s in payload.get("signals", [])}
        core = [by_name.get(n) for n in ("gpu_utilization_pct", "render_queue_depth", "render_latency_s",
                                          "worker_error_rate_per_min") if by_name.get(n)]
        log_id = by_name.get("worker_error_logs")
        return {
            "hypotheses": [
                {
                    "cause": "Render worker pool saturation (GPU-bound)",
                    "confidence": 0.87,
                    "supporting_ids": [i for i in core + [log_id] if i],
                    "contradicting_ids": [],
                    "contradiction_notes": "",
                    "severity": "HIGH",
                    "affected": "Render Pipeline — Worker Pool A",
                },
                {
                    "cause": "Deployment regression in render workers",
                    "confidence": 0.22,
                    "supporting_ids": [i for i in [log_id] if i],
                    "contradicting_ids": [i for i in [by_name.get("gpu_utilization_pct")] if i],
                    "contradiction_notes": "No deploy markers in the log window; saturation predates errors.",
                    "severity": "MEDIUM",
                    "affected": "Render Pipeline",
                },
                {
                    "cause": "Upstream asset-storage dependency failure",
                    "confidence": 0.12,
                    "supporting_ids": [],
                    "contradicting_ids": [i for i in core if i][:2],
                    "contradiction_notes": "Latency growth tracks GPU load, not I/O wait.",
                    "severity": "MEDIUM",
                    "affected": "Asset Storage",
                },
            ]
        }

    def _risk_projection(self, payload: dict) -> dict:
        eta = payload.get("eta_minutes")
        breached = payload.get("breached")
        event = ("Render queue capacity already exceeded" if breached
                 else "Render queue exceeds capacity")
        return {
            "event": event,
            "at_risk": f"{payload.get('at_risk_jobs', 'queued jobs')} at risk"
                       + (f" within ~{round(eta)} minutes" if eta else ""),
            "basis": f"queue at {payload.get('current')} of {payload.get('capacity')} capacity, "
                     f"slope {payload.get('slope_per_min')}/min (computed from retrieved telemetry)",
        }

    def _remediation_plan(self, payload: dict) -> dict:
        return {
            "action": "Reduce render concurrency by 20% and redirect queued jobs to Worker Pool B",
            "expected_effects": [
                "Reduce GPU saturation",
                "Prevent queue overflow",
                "Lower timeout probability",
            ],
            "risk": "MEDIUM",
            "actuation": {"type": "concurrency", "factor": 0.8},
        }


def get_cognition(settings: Settings) -> Cognition:
    if settings.gemini_live:
        return GeminiCognition(settings)
    return MockCognition()
