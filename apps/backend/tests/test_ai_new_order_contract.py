"""Canonical B output and independently versioned public AI schema must agree."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from test_extraction_batch3 import _suggestion_payload, _validate

ROOT = Path(__file__).resolve().parents[3]


def validator():
    registry = Registry()
    for path in (ROOT / "contracts").rglob("*.schema.json"):
        registry = registry.with_resource(
            path.as_uri(), Resource.from_contents(json.loads(path.read_text()))
        )
    schema = ROOT / "contracts/ai/change-proposal.schema.json"
    return Draft202012Validator(
        {"$ref": schema.as_uri()}, registry=registry, format_checker=FormatChecker()
    )


@pytest.mark.parametrize("suggestion", [True, False])
def test_canonical_output_is_valid_in_public_ai_contract(suggestion):
    payload = _suggestion_payload()
    if not suggestion:
        payload.pop("new_work_order")
    value = _validate(payload).model_dump(mode="json")
    assert not list(validator().iter_errors(value))


@pytest.mark.parametrize("case", ["execution", "matched"])
def test_suggestions_never_carry_execution_authority_or_existing_assignment(case):
    value = _validate(_suggestion_payload()).model_dump(mode="json")
    if case == "execution":
        value["new_work_order"]["approved"] = True
    else:
        value.update(
            assignment="matched",
            work_order_id="00000000-0000-4000-8000-000000000003",
            base_work_order_version=3,
        )
    assert list(validator().iter_errors(value))
