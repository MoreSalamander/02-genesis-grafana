"""Temporal workflow — the locked operational loop as durable execution.

Deterministic orchestration only (activities are referenced by name); the
Studio Head's authorization is a workflow SIGNAL: the loop pauses durably at
the human boundary and survives worker crashes, restarts, and long waits —
the preserved-stack responsibility Temporal owns ("human approval pauses,
retries, durable execution state").
"""
from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

_RETRY = RetryPolicy(initial_interval=timedelta(seconds=3), maximum_attempts=3)
_OPTS = {"start_to_close_timeout": timedelta(minutes=4), "retry_policy": _RETRY}
DECISION_WINDOW = timedelta(hours=24)


@workflow.defn(name="InvestigationWorkflow")
class InvestigationWorkflow:
    def __init__(self) -> None:
        self._decision: str | None = None

    @workflow.signal(name="studio_head_decision")
    def studio_head_decision(self, decision: str) -> None:
        if self._decision is None and decision in ("approved", "rejected"):
            self._decision = decision

    @workflow.query(name="decision")
    def decision(self) -> str | None:
        return self._decision

    @workflow.run
    async def run(self, inv_id: str) -> str:
        try:
            status = await workflow.execute_activity("ops.observe", inv_id, **_OPTS)
            if status == "HEALTHY":
                return status

            await workflow.execute_activity("ops.correlate", inv_id, **_OPTS)
            await workflow.execute_activity("ops.diagnose", inv_id, **_OPTS)
            await workflow.execute_activity("ops.predict", inv_id, **_OPTS)
            await workflow.execute_activity("ops.recommend", inv_id, **_OPTS)
        except ActivityError as err:
            # exhausted retries → honest INCOMPLETE (§15), latch released in finalize
            return await workflow.execute_activity(
                "ops.incomplete",
                args=[inv_id, f"Durable stage failed after retries: {err.__cause__ or err}"],
                **_OPTS,
            )

        # Human boundary (locked §10): durable pause until the Studio Head decides.
        try:
            await workflow.wait_condition(lambda: self._decision is not None, timeout=DECISION_WINDOW)
        except TimeoutError:
            return await workflow.execute_activity("ops.escalate_timeout", inv_id, **_OPTS)

        if self._decision == "rejected":
            return await workflow.execute_activity("ops.decide_reject", inv_id, **_OPTS)

        acted = await workflow.execute_activity("ops.act", inv_id, **_OPTS)
        if not acted:
            return "REMEDIATION_FAILED"
        return await workflow.execute_activity(
            "ops.verify", inv_id,
            start_to_close_timeout=timedelta(minutes=6),
            retry_policy=RetryPolicy(maximum_attempts=1),  # verification is judgment, not retryable IO
        )
