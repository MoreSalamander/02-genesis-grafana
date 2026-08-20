"""Mirror the provisioned Grafana surfaces to the Grafana Cloud stack.

The local files are the source of truth (datasource uids prometheus/loki/
tempo); this script rewrites those uids to the Cloud stack's
(grafanacloud-prom / grafanacloud-logs / grafanacloud-traces), pushes the
dashboards into a "Genesis Ops" folder, and provisions the same four alert
rules there. Re-runnable: dashboards overwrite, rules delete-and-recreate.

Usage:  cd ops && python3 push_to_cloud.py     (reads ./.env)
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

import httpx
import yaml

HERE = pathlib.Path(__file__).parent
UID_MAP = {
    '"uid": "prometheus"': '"uid": "grafanacloud-prom"',
    '"uid": "loki"': '"uid": "grafanacloud-logs"',
    '"uid": "tempo"': '"uid": "grafanacloud-traces"',
}
DS_MAP = {"prometheus": "grafanacloud-prom", "loki": "grafanacloud-logs",
          "tempo": "grafanacloud-traces", "__expr__": "__expr__"}
DASHBOARDS = ["the-slate.json", "farm-floor.json", "the-agent.json", "studio-operations.json"]


def env() -> tuple[str, str]:
    for line in (HERE / ".env").read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())
    url = os.environ["MCP_TARGET_GRAFANA_URL"].rstrip("/")
    token = os.environ["GRAFANA_SA_TOKEN"]
    return url, token


def main() -> int:
    url, token = env()
    c = httpx.Client(base_url=url, headers={
        "Authorization": f"Bearer {token}",
        "X-Disable-Provenance": "true",   # allow API-managed rules
    }, timeout=30)

    # Folder for everything Genesis.
    folders = {f["title"]: f["uid"] for f in c.get("/api/folders").json()}
    if "Genesis Ops" in folders:
        folder_uid = folders["Genesis Ops"]
    else:
        folder_uid = c.post("/api/folders", json={"title": "Genesis Ops"}).json()["uid"]
    print(f"folder Genesis Ops = {folder_uid}")

    # Dashboards, uids rewritten to the Cloud datasources.
    for name in DASHBOARDS:
        path = HERE / "dashboards" / name
        if not path.exists():
            continue
        raw = path.read_text()
        for a, b in UID_MAP.items():
            raw = raw.replace(a, b)
        dash = json.loads(raw)
        dash.pop("id", None)
        r = c.post("/api/dashboards/db", json={
            "dashboard": dash, "overwrite": True, "folderUid": folder_uid,
            "message": "mirrored from repo provisioning",
        })
        print(f"dashboard {dash['uid']}: HTTP {r.status_code}"
              + ("" if r.status_code == 200 else f" — {r.text[:160]}"))

    # Alert rules from the same YAML the local stack provisions.
    spec = yaml.safe_load((HERE / "provisioning/alerting/genesis-rules.yml").read_text())
    for group in spec["groups"]:
        for rule in group["rules"]:
            for d in rule["data"]:
                d["datasourceUid"] = DS_MAP.get(d["datasourceUid"], d["datasourceUid"])
            body = {
                "title": rule["title"], "uid": rule["uid"],
                "ruleGroup": group["name"], "folderUID": folder_uid,
                "condition": rule["condition"], "data": rule["data"],
                "noDataState": rule["noDataState"], "execErrState": rule["execErrState"],
                "for": rule["for"], "annotations": rule.get("annotations", {}),
                "labels": rule.get("labels", {}), "orgID": 1,
            }
            c.delete(f"/api/v1/provisioning/alert-rules/{rule['uid']}")  # idempotent re-push
            r = c.post("/api/v1/provisioning/alert-rules", json=body)
            print(f"rule {rule['uid']}: HTTP {r.status_code}"
                  + ("" if r.status_code in (200, 201) else f" — {r.text[:160]}"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
