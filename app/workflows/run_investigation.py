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


@lru_cache(maxsize=1)
def get_runtime() -> Runtime:
    bus = EventBus(settings.data_dir)
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
    return Runtime(settings=settings, bus=bus, working=WorkingMemory(),
                   episodic=executive.episodic, executive=executive)


def start_investigation(question: str) -> Investigation:
    runtime = get_runtime()
    inv = Investigation(question=question)
    runtime.working.put(inv)
    return inv


def run_investigation(inv_id: str) -> None:
    runtime = get_runtime()
    inv = runtime.working.get(inv_id)
    if inv is not None:
        runtime.executive.investigate(inv)


def run_decision(inv_id: str, decision: str) -> None:
    runtime = get_runtime()
    inv = runtime.working.get(inv_id)
    if inv is not None:
        runtime.executive.execute_decision(inv, decision)
