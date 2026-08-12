"""Contextual interpretation layer (locked §11/§13): Grafana answers *what is
happening*; this graph answers *what the thing is and what it belongs to* —
Service → Pipeline → Project → Department. Agents receive the smallest relevant
scope, not the whole studio. (DataHub carries this role in the production
architecture; the standalone MVP keeps the same shape locally.)
"""
from __future__ import annotations

STUDIO_OPS_CONTEXT = (
    "Convergence Studios operations. The render pipeline turns approved shots into final frames; "
    "queue overflow halts downstream compositing and review. Worker Pool A is GPU-bound; Worker "
    "Pool B has headroom for redirected jobs. Bounded operational interventions are permitted only "
    "after Studio Head authorization."
)

SERVICE_GRAPH: dict[str, dict] = {
    "render-worker": {
        "service": "render-worker",
        "pipeline": "Render Pipeline",
        "project": "Nebula Frontier",
        "department": "Production",
    },
}


def scope_for(service: str) -> list[str]:
    node = SERVICE_GRAPH.get(service, {})
    return [
        "Convergence Studios",
        "Operations",
        node.get("department", "Production"),
        node.get("project", "Active Production"),
        node.get("pipeline", service),
    ]
