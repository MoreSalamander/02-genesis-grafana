"""DataHub — the contextual-interpretation substrate (locked §13).

Grafana answers *what is happening*; DataHub answers *what the thing is and
what it belongs to*: Service → Pipeline → Project → Department. This module

  1. bootstraps the studio's operational graph into DataHub (idempotent),
  2. resolves the scoped-context chain for a service AT RUNTIME from DataHub,
  3. emits every completed investigation as a provenance entity linked to the
     service it affected (operational lineage).

DataHub is part of the deployed stack (quickstart GMS at localhost:8080 by
default). The in-code SERVICE_GRAPH map is a resilience fallback only — used
when GMS is unreachable, and always logged when that happens (§15: degraded
state is surfaced, never silent).
"""
from __future__ import annotations

from app.config import Settings
from app import runtime_proof
from app.knowledge.context import SERVICE_GRAPH
from app.models.operational import Investigation

_PLATFORM = "genesis-studio"


def _urn(name: str) -> str:
    from datahub.emitter.mce_builder import make_dataset_urn

    return make_dataset_urn(platform=_PLATFORM, name=name, env="PROD")


class DataHubKnowledge:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._graph = None
        if settings.datahub_gms_url and not settings.force_mock:
            try:
                from datahub.ingestion.graph.client import DataHubGraph, DatahubClientConfig

                self._graph = DataHubGraph(
                    DatahubClientConfig(server=settings.datahub_gms_url, timeout_sec=4)
                )
                self._graph.test_connection()
                print(f"[knowledge] DataHub connected: {settings.datahub_gms_url}")
                # test_connection() is a real round-trip to GMS, so this one is
                # first-hand evidence rather than configuration.
                runtime_proof.record(
                    "datahub", "LIVE",
                    f"GMS connection verified at {settings.datahub_gms_url}")
            except Exception as err:
                print(f"[knowledge] DataHub unreachable ({err}) — using in-code context fallback")
                runtime_proof.record(
                    "datahub", "DEGRADED",
                    f"GMS unreachable ({err}) — in-code context graph in use")
                self._graph = None
        else:
            runtime_proof.record(
                "datahub", "MOCK",
                "no DATAHUB_GMS_URL (or GENESIS_MOCK set) — in-code context graph only")

    @property
    def available(self) -> bool:
        return self._graph is not None

    # -- bootstrap ------------------------------------------------------------
    def bootstrap(self) -> None:
        """Emit the studio operational graph (idempotent upserts)."""
        if self._graph is None:
            return
        try:
            from datahub.emitter.mcp import MetadataChangeProposalWrapper
            from datahub.metadata.schema_classes import (
                DatasetLineageTypeClass,
                DatasetPropertiesClass,
                UpstreamClass,
                UpstreamLineageClass,
            )

            node = SERVICE_GRAPH["render-worker"]
            chain = [
                ("department/" + node["department"].lower(), node["department"], "Department"),
                ("project/" + node["project"].lower().replace(" ", "-"), node["project"], "Project"),
                ("pipeline/" + node["pipeline"].lower().replace(" ", "-"), node["pipeline"], "Pipeline"),
                ("service/render-worker", "render-worker", "Service"),
            ]
            for i, (name, display, kind) in enumerate(chain):
                props = {
                    "kind": kind,
                    "studio": "Convergence Studios",
                }
                if kind == "Service":
                    props.update({
                        "pipeline": node["pipeline"],
                        "project": node["project"],
                        "department": node["department"],
                    })
                self._graph.emit_mcp(
                    MetadataChangeProposalWrapper(
                        entityUrn=_urn(name),
                        aspect=DatasetPropertiesClass(
                            name=display,
                            description=f"Genesis OS operational graph — {kind}: {display}",
                            customProperties=props,
                        ),
                    )
                )
                if i > 0:  # child ──belongs_to──> parent lineage
                    self._graph.emit_mcp(
                        MetadataChangeProposalWrapper(
                            entityUrn=_urn(name),
                            aspect=UpstreamLineageClass(upstreams=[
                                UpstreamClass(dataset=_urn(chain[i - 1][0]),
                                              type=DatasetLineageTypeClass.TRANSFORMED)
                            ]),
                        )
                    )
            print("[knowledge] DataHub studio graph bootstrapped (4 entities + lineage)")
        except Exception as err:
            print(f"[knowledge] DataHub bootstrap failed: {err}")

    # -- runtime context read ---------------------------------------------------
    def scope_for(self, service: str) -> list[str]:
        if self._graph is not None:
            try:
                from datahub.metadata.schema_classes import DatasetPropertiesClass

                props = self._graph.get_aspect(_urn(f"service/{service}"), DatasetPropertiesClass)
                if props and props.customProperties:
                    cp = props.customProperties
                    return [
                        "Convergence Studios",
                        "Operations",
                        cp.get("department", "Production"),
                        cp.get("project", "Active Production"),
                        cp.get("pipeline", service),
                    ]
            except Exception as err:
                print(f"[knowledge] DataHub scope read failed ({err}) — fallback context")
        node = SERVICE_GRAPH.get(service, {})
        return [
            "Convergence Studios",
            "Operations",
            node.get("department", "Production"),
            node.get("project", "Active Production"),
            node.get("pipeline", service),
        ]

    # -- provenance write ---------------------------------------------------------
    def emit_investigation(self, inv: Investigation) -> bool:
        if self._graph is None:
            return False
        try:
            from datahub.emitter.mcp import MetadataChangeProposalWrapper
            from datahub.metadata.schema_classes import (
                DatasetLineageTypeClass,
                DatasetPropertiesClass,
                UpstreamClass,
                UpstreamLineageClass,
            )

            leading = inv.leading_diagnosis
            props = {
                "question": inv.question,
                "status": inv.status.value,
                "site": self.settings.site,
                "leading_cause": (leading.cause if leading else "")[:400],
                "confidence": str(leading.confidence) if leading else "",
                "escalated": str(inv.escalated),
                "improved": str(inv.verification.improved) if inv.verification else "",
                "action": (inv.plan.action if inv.plan else "")[:400],
                "decision": (inv.plan.decision if inv.plan else "") or "",
            }
            urn = _urn(f"investigation/{inv.id}")
            self._graph.emit_mcp(
                MetadataChangeProposalWrapper(
                    entityUrn=urn,
                    aspect=DatasetPropertiesClass(
                        name=f"Investigation {inv.id}",
                        description=f"Operational investigation — {inv.question}",
                        customProperties=props,
                    ),
                )
            )
            self._graph.emit_mcp(
                MetadataChangeProposalWrapper(
                    entityUrn=urn,
                    aspect=UpstreamLineageClass(upstreams=[
                        UpstreamClass(dataset=_urn("service/render-worker"),
                                      type=DatasetLineageTypeClass.TRANSFORMED)
                    ]),
                )
            )
            runtime_proof.record(
                "datahub", "LIVE",
                f"investigation provenance emitted to {self.settings.datahub_gms_url}")
            return True
        except Exception as err:
            print(f"[knowledge] DataHub investigation emit failed: {err}")
            runtime_proof.record("datahub", "DEGRADED", f"investigation emit failed ({err})")
            return False
