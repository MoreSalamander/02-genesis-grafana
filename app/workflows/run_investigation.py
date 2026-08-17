"""Investigation workflow wiring — assembles the operational cognition hierarchy
once and runs investigations through it."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from app.agents.correlation.correlator import CorrelationAgent
from app.agents.diagnosis.diagnostician import DiagnosisAgent
from app.agents.executive.executive import OperationalExecutive
from app.agents.prediction.predictor import PredictionAgent
from app.agents.remediation.planner import RemediationAgent
from app.config import Settings, settings
from app import runtime_proof
from app.events.bus import EventBus
from app.knowledge.datahub import DataHubKnowledge
from app.memory.stores import EpisodicMemory, WorkingMemory
from app.models.operational import Investigation
from app.tools.google.gemini import get_cognition
from app.tools.grafana.mcp_client import get_telemetry
from app.tools.studio.control import StudioControl


@dataclass
class Runtime:
    settings: Settings
    bus: EventBus
    working: WorkingMemory
    episodic: EpisodicMemory
    executive: OperationalExecutive
    ephemeral: object = None


@lru_cache(maxsize=1)
def get_runtime() -> Runtime:
    from app.observability.tracing import setup_tracing

    setup_tracing(settings, "genesis-ops")
    bus = EventBus(
        settings.data_dir,
        nats_url="" if settings.force_mock else settings.nats_url,
        subject=settings.nats_subject,
    )
    cognition = get_cognition(settings)
    telemetry = get_telemetry(settings)
    knowledge = DataHubKnowledge(settings)
    knowledge.bootstrap()
    executive = OperationalExecutive(
        settings=settings,
        telemetry=telemetry,
        control=StudioControl(settings),
        correlator=CorrelationAgent(cognition, bus),
        diagnostician=DiagnosisAgent(cognition, bus),
        predictor=PredictionAgent(cognition, bus, settings.thresholds),
        remediation=RemediationAgent(cognition, bus),
        episodic=EpisodicMemory(settings.data_dir),
        bus=bus,
        knowledge=knowledge,
    )
    from app.memory.durable import get_store
    from app.memory.ephemeral import get_ephemeral

    ephemeral = get_ephemeral(settings)
    executive.ephemeral = ephemeral  # released at investigation finalize
    return Runtime(settings=settings, bus=bus, working=WorkingMemory(get_store(settings)),
                   episodic=executive.episodic, executive=executive, ephemeral=ephemeral)


def start_investigation(question: str) -> Investigation:
    runtime = get_runtime()
    inv = Investigation(question=question)
    runtime.working.put(inv)
    return inv


def run_investigation(inv_id: str) -> None:
    from app import cognition_ledger

    runtime = get_runtime()
    inv = runtime.working.get(inv_id)
    if inv is not None:
        # Tag every model call made inside the loop with the run that caused
        # it, so the console can show the reasoning behind one investigation
        # rather than an undifferentiated stream of calls.
        with cognition_ledger.context(inv_id):
            runtime.executive.investigate(inv)
        runtime.working.put(inv)  # durable checkpoint


def run_decision(inv_id: str, decision: str) -> None:
    from app import cognition_ledger

    runtime = get_runtime()
    inv = runtime.working.get(inv_id)
    if inv is not None:
        with cognition_ledger.context(inv_id):
            runtime.executive.execute_decision(inv, decision)
        runtime.working.put(inv)  # durable checkpoint


# ---------------------------------------------------------------------------
# Temporal dispatch (durable execution — preserved-stack responsibility).
# The in-process path above remains as a surfaced-degradation fallback.
# ---------------------------------------------------------------------------

def _workflow_id(inv_id: str) -> str:
    return f"inv-wf-{inv_id}"


def dispatch_investigation(inv_id: str) -> str:
    """Returns 'temporal' when the durable workflow started, else 'local'."""
    if settings.force_mock:
        runtime_proof.record("temporal", "MOCK",
                             "GENESIS_MOCK set — in-process execution by design")
        return "local"
    if not settings.temporal_address:
        # Not part of this deployment (e.g. Cloud Run). Attempting a dial would
        # report DEGRADED, which reads as a fault rather than an absent
        # substrate — so say what is actually true and run in-process.
        runtime_proof.record("temporal", "MOCK",
                             "no TEMPORAL_ADDRESS — in-process execution for this deployment")
        return "local"
    try:
        import asyncio

        from temporalio.client import Client

        async def go():
            client = await Client.connect(settings.temporal_address)
            await client.start_workflow(
                "InvestigationWorkflow", inv_id,
                id=_workflow_id(inv_id), task_queue=settings.temporal_task_queue,
            )

        asyncio.run(go())
        runtime_proof.record("temporal", "LIVE",
                             f"durable workflow accepted at {settings.temporal_address}")
        return "temporal"
    except Exception as err:
        print(f"[workflow] Temporal dispatch failed ({err}) — DEGRADED: in-process execution")
        runtime_proof.record("temporal", "DEGRADED",
                             f"dispatch failed ({err}) — ran in-process instead")
        return "local"


def dispatch_decision(inv_id: str, decision: str) -> str:
    """Signals the durable workflow's human boundary; 'local' on fallback."""
    if settings.force_mock:
        runtime_proof.record("temporal", "MOCK",
                             "GENESIS_MOCK set — in-process execution by design")
        return "local"
    if not settings.temporal_address:
        # Not part of this deployment (e.g. Cloud Run). Attempting a dial would
        # report DEGRADED, which reads as a fault rather than an absent
        # substrate — so say what is actually true and run in-process.
        runtime_proof.record("temporal", "MOCK",
                             "no TEMPORAL_ADDRESS — in-process execution for this deployment")
        return "local"
    try:
        import asyncio

        from temporalio.client import Client

        async def go():
            client = await Client.connect(settings.temporal_address)
            handle = client.get_workflow_handle(_workflow_id(inv_id))
            await handle.signal("studio_head_decision", decision)

        asyncio.run(go())
        runtime_proof.record("temporal", "LIVE",
                             f"durable workflow accepted at {settings.temporal_address}")
        return "temporal"
    except Exception as err:
        print(f"[workflow] Temporal signal failed ({err}) — DEGRADED: in-process execution")
        runtime_proof.record("temporal", "DEGRADED",
                             f"signal failed ({err}) — handled in-process instead")
        return "local"
