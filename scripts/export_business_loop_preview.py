"""Copy a pinned candidate contract; never register it as implemented routes."""

import json
import subprocess
import re
from pathlib import Path

ref = "d696735623b52e4d5135c40a62e6b0744cc31af2"
candidate = json.loads(
    subprocess.check_output(["git", "show", ref + ":contracts/openapi.json"])
)
current = json.loads(
    subprocess.check_output(
        [
            "git",
            "show",
            "e912977f0a9d75f549c540a0f318fed4344f0433:contracts/openapi.json",
        ]
    )
)
paths = {p: v for p, v in candidate["paths"].items() if p not in current["paths"]}
for p in [
    "/api/v1/work-orders/{order_id}/status",
    "/api/v1/work-orders/{order_id}/changes/{change_id}/confirm",
]:
    paths[p] = candidate["paths"][p]
schemas = {}
queue = re.findall(r'#/components/schemas/([^"\\]+)', json.dumps(paths))
while queue:
    k = queue.pop()
    if k in schemas:
        continue
    schemas[k] = candidate["components"]["schemas"][k]
    queue.extend(re.findall(r'#/components/schemas/([^"\\]+)', json.dumps(schemas[k])))
doc = {
    "openapi": "3.1.0",
    "info": {
        "title": "Pending business-loop client contract; not implemented main API",
        "version": "0.1.0",
        "x-source-commit": ref,
        "description": "Read-only snapshot from PR32. Availability requires explicit reviewed backend capability; never permission or implementation evidence.",
    },
    "paths": paths,
    "components": {"schemas": dict(sorted(schemas.items()))},
}
Path("contracts/business-loop-preview.openapi.json").write_text(
    json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
)
print(len(paths), "pending paths;", len(schemas), "referenced schemas")
