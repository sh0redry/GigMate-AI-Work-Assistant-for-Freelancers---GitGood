import json

import pytest
from pydantic import TypeAdapter, ValidationError

from gigmate import contracts
from gigmate.config import ROOT

EXAMPLES = ROOT / "contracts/examples"
MANIFEST = json.loads((EXAMPLES / "manifest.json").read_text(encoding="utf-8"))
DOMAIN_FIXTURES = [item for item in MANIFEST["fixtures"] if "/domain/" in item["schema"]]


@pytest.mark.parametrize("item", DOMAIN_FIXTURES, ids=lambda item: item["file"])
def test_original_domain_fixtures_match_canonical_runtime_models(item):
    name = item["schema"].split("/$defs/")[-1]
    adapter = TypeAdapter(getattr(contracts, name))
    value = (EXAMPLES / item["file"]).read_text(encoding="utf-8")
    if item["valid"]:
        adapter.validate_json(value)
    else:
        with pytest.raises(ValidationError):
            adapter.validate_json(value)
