"""HTTP interface for the incident console (frontend/) and for the eventual
Genesis OS Operational Intelligence Contract adapter. The standalone owns this
API; the federation consumes it — never the reverse.
"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from app.governance.authority import AuthorityError, VALID_DECISIONS
from app.models.operational import Investigation
from app.workflows.run_investigation import (
    dispatch_decision,
    dispatch_investigation,
    get_runtime,
    run_decision,
    run_investigation,
    start_investigation,
)
from app import runtime_proof

router = APIRouter(prefix="/api")


class InvestigationRequest(BaseModel):
    question: str = Field(min_length=5, max_length=300, default="How is production doing right now?")


class DecisionRequest(BaseModel):
    decision: str  # approved | rejected


def _summary(inv: Investigation) -> dict:
    leading = inv.leading_diagnosis
    return {
        "id": inv.id,
        "question": inv.question,
        "status": inv.status.value,
        "severity": leading.severity.value if leading else None,
        "leading_cause": leading.cause if leading else None,
        "confidence": leading.confidence if leading else None,
        "escalated": inv.escalated,
        "created_at": inv.created_at,
        "updated_at": inv.updated_at,
    }


@router.get("/status")
def status() -> dict:
    runtime = get_runtime()
    return {
        "system": "Genesis OS — Operational Intelligence",
        "banner": runtime.settings.banner(),
        "grafana_live": runtime.settings.grafana_live,
        "gemini_live": runtime.settings.gemini_live,
        "investigations": len(runtime.working.all()),
        "runtime_proof": _runtime_proof(runtime.settings),
    }


def _runtime_proof(settings) -> dict:
    """Substrate states for the console's runtime-proof footer.

    These are configuration-derived starting points; app.runtime_proof
    overrides any of them the moment the substrate is actually exercised, so a
    chip only reads LIVE on evidence.
    """
    return runtime_proof.snapshot({
        "gemini": (("LIVE", f"credential present — narration via {settings.gemini_model}")
                   if settings.gemini_live
                   else ("MOCK", "no GOOGLE_API_KEY — deterministic mock narration")),
        # settings.grafana_live only asserts that a URL string is configured — it
        # says nothing about whether anything answers there. A hosted deployment
        # pointed at an unreachable MCP endpoint would otherwise advertise LIVE
        # on the very claim this track is judged on. So the configured state is
        # IDLE, and only a returned MCP call (recorded in mcp_client._call)
        # upgrades it to LIVE.
        "grafana": (("IDLE", f"MCP configured at {settings.grafana_mcp_url} — not yet queried")
                    if settings.grafana_live
                    else ("MOCK", "no Grafana MCP URL — simulated render-farm telemetry")),
        # An unset address means Temporal is not part of this deployment, not
        # that it broke — dialling it would report DEGRADED and read as a fault.
        "temporal": (("IDLE", f"configured at {settings.temporal_address} — "
                              "no workflow dispatched yet this session")
                     if settings.temporal_address
                     else ("MOCK", "no TEMPORAL_ADDRESS — in-process execution for this deployment")),
        "datahub": ("IDLE", f"configured at {settings.datahub_gms_url} — not contacted yet"),
    })


@router.post("/investigations", status_code=202)
def create_investigation(body: InvestigationRequest, background: BackgroundTasks) -> dict:
    from app.memory.ephemeral import INVESTIGATION_LATCH, LATCH_TTL_S

    runtime = get_runtime()
    # Latch FIRST — a blocked attempt must not persist a phantom investigation.
    inv = Investigation(question=body.question)
    holder = runtime.ephemeral.acquire_latch(INVESTIGATION_LATCH, inv.id, LATCH_TTL_S)
    if holder is not None:
        raise HTTPException(
            409, f"an investigation is already active ({holder}) — one operational reality at a time"
        )
    runtime.working.put(inv)
    execution = dispatch_investigation(inv.id)
    if execution == "local":
        background.add_task(run_investigation, inv.id)
    return {"id": inv.id, "status": inv.status.value, "execution": execution}


@router.get("/investigations")
def list_investigations() -> list[dict]:
    return [_summary(i) for i in get_runtime().working.all()]


@router.get("/investigations/{inv_id}")
def get_investigation(inv_id: str) -> dict:
    inv = get_runtime().working.get(inv_id)
    if inv is None:
        raise HTTPException(404, "investigation not found")
    return inv.model_dump(mode="json")


@router.post("/investigations/{inv_id}/decision", status_code=202)
def decide(inv_id: str, body: DecisionRequest, background: BackgroundTasks) -> dict:
    runtime = get_runtime()
    inv = runtime.working.get(inv_id)
    if inv is None:
        raise HTTPException(404, "investigation not found")
    if body.decision not in VALID_DECISIONS:
        raise HTTPException(400, f"decision must be one of {sorted(VALID_DECISIONS)}")
    if inv.plan is None or inv.plan.decision is not None:
        raise HTTPException(400, "no remediation plan awaiting a decision")
    # The decision is a durable workflow signal; act + verify continue in the workflow.
    execution = dispatch_decision(inv.id, body.decision)
    if execution == "local":
        background.add_task(run_decision, inv.id, body.decision)
    return {"id": inv.id, "decision": body.decision, "status": "processing", "execution": execution}


@router.delete("/investigations/{inv_id}", status_code=200)
def clear_investigation(inv_id: str) -> dict:
    """End an investigation and remove it.

    A run that is still mid-loop is marked ABANDONED before it goes, so the
    record of what happened is truthful for as long as it exists: it did not
    finish, and nothing here pretends it concluded anything. The Temporal
    workflow may still be in flight — it writes to an id that no longer
    resolves, which is harmless, and the console stops showing a run that is
    going nowhere.
    """
    runtime = get_runtime()
    inv = runtime.working.get(inv_id)
    if inv is None:
        raise HTTPException(404, "investigation not found")

    was = inv.status.value
    running = was in {
        "OBSERVING", "CORRELATING", "DIAGNOSING", "PREDICTING",
        "AWAITING_AUTHORIZATION", "ACTING", "VERIFYING",
    }
    runtime.bus.emit(
        "investigation.cleared",
        investigation_id=inv_id, was=was, running=running,
    )
    removed = runtime.working.drop(inv_id)
    return {"id": inv_id, "removed": removed, "was": was, "was_running": running}


@router.get("/events")
def events(limit: int = 150) -> list[dict]:
    return get_runtime().bus.tail(limit)


@router.get("/memory/episodic")
def episodic(limit: int = 50) -> list[dict]:
    return get_runtime().episodic.list(limit)


# --- the render farm itself -----------------------------------------------
# The console draws the farm the agent is investigating. It reads through this
# API rather than calling the simulator directly so that the browser has one
# origin, and so a hosted console can reach a farm that is not on localhost.
#
# This is the environment, not the agent's findings: these numbers are the
# farm's own state, not something the loop concluded. The console labels them
# that way.

@router.get("/farm")
def farm() -> dict:
    import httpx

    from app.config import settings

    try:
        res = httpx.get(f"{settings.simulator_control_url}/farm", timeout=4.0)
        res.raise_for_status()
        return res.json()
    except Exception as err:
        # A farm we cannot reach is reported as unreachable. Returning a shape
        # full of zeroes would draw an idle farm, which is a different claim.
        raise HTTPException(503, f"render farm unreachable at {settings.simulator_control_url}: {err}")


@router.post("/farm/scenario/{key}")
def farm_scenario(key: str) -> dict:
    """Begin (or clear) an incident on the farm. This is a demo control: it
    changes the world the agent observes, never the agent's conclusions."""
    import httpx

    from app.config import settings

    try:
        res = httpx.post(f"{settings.simulator_control_url}/scenario/{key}", timeout=4.0)
        res.raise_for_status()
        return res.json()
    except Exception as err:
        raise HTTPException(503, f"could not reach the render farm: {err}")


@router.post("/farm/auto/{state}")
def farm_auto(state: str) -> dict:
    """Unattended mode: the farm cycles through incidents on its own."""
    import httpx

    from app.config import settings

    try:
        res = httpx.post(f"{settings.simulator_control_url}/scenario/auto/{state}", timeout=4.0)
        res.raise_for_status()
        return res.json()
    except Exception as err:
        raise HTTPException(503, f"could not reach the render farm: {err}")


# --- the reasoning itself -------------------------------------------------
# What the model was asked and what it said, recorded at the moment of the
# call (app/cognition_ledger.py). The list stays light because prompts carry
# whole telemetry payloads; the full text is fetched per call when opened.

@router.get("/cognition")
def cognition(limit: int = 40, ref: str = "") -> list[dict]:
    from app import cognition_ledger

    return cognition_ledger.tail(limit=limit, ref=ref or None)


@router.get("/cognition/{cog_id}")
def cognition_detail(cog_id: str) -> dict:
    from app import cognition_ledger

    entry = cognition_ledger.get(cog_id)
    if entry is None:
        raise HTTPException(404, "no such model call")
    return entry
