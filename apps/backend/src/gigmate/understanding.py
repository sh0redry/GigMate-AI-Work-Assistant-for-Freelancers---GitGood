"""Two fixed fictional examples, deliberately not a general language model."""

import copy
import json
from uuid import uuid4

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from gigmate.config import ROOT
from gigmate.messaging import fixture


def extract(event, order, context_version):
    if event["event_type"] != "message.created":
        return None
    template = fixture("message-reschedule")
    available_text = "确认下星期四下午四点半到五点半，地址晚些发"
    if event["payload"]["text"] not in {template["payload"]["text"], available_text}:
        return None
    proposal = copy.deepcopy(fixture("proposal-reschedule"))
    proposal.update(
        proposal_id=str(uuid4()),
        work_order_id=order["id"],
        conversation_id=event["conversation_id"],
        base_work_order_version=order["version"],
        base_context_version=context_version,
    )
    proposal["candidates"] = [{"work_order_id": order["id"], "confidence": 1.0}]
    change = proposal["changes"][0]
    change["old_value"] = order["fields"]["schedule"]["value"]
    change["sources"] = [
        {
            "message_id": event["payload"]["message_id"],
            "message_revision": event["message_revision"],
        }
    ]
    if event["payload"]["text"] == available_text:
        change["new_value"].update(start_at="2026-10-08T08:30:00Z", end_at="2026-10-08T09:30:00Z")
        proposal["unresolved_questions"] = ["见面地址尚未提供"]
        change["customer_confirmation"] = "confirmed"
    registry = Registry()
    for path in (ROOT / "contracts").glob("**/*.schema.json"):
        registry = registry.with_resource(
            path.as_uri(), Resource.from_contents(json.loads(path.read_text(encoding="utf-8")))
        )
    Draft202012Validator(
        {"$ref": (ROOT / "contracts/ai/change-proposal.schema.json").as_uri()},
        registry=registry,
        format_checker=FormatChecker(),
    ).validate(proposal)
    return proposal
