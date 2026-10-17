"""Report whether this installation is privately configured for live models.

The report is for the operator who owns the credentials: it reads only the
process environment and never prints a secret, a key prefix or an endpoint
credential. A "ready" line means *configuration is complete*; it is not
acceptance of vendor quality, price or of any real customer run.

Usage::

    .venv/bin/python scripts/check_model_config.py
    .venv/bin/python scripts/check_model_config.py --json

Exit status is 0 when every checked gate is configured, 1 when something is
missing, so the script can run before a deployment starts.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/backend/src"))

from gigmate.extraction.llm import (  # noqa: E402
    LLMProvider,
    validate_provider_config,
)
from gigmate import secrets  # noqa: E402
from gigmate.media import llm as media_llm  # noqa: E402

# Presence only: the value itself never leaves the process.
PRESENCE_VARS = {
    "GIGMATE_LLM_PROVIDER": "text vendor",
    "GIGMATE_LLM_MODEL": "text model",
    "GIGMATE_LLM_API_KEY": "text credential (value never printed)",
    "GIGMATE_LLM_LIVE": "text live gate",
    "GIGMATE_LLM_ALLOW_LIVE_ORIGIN": "text live-origin gate",
    "GIGMATE_LLM_COST_BUDGET_USD": "cost budget per call",
    "GIGMATE_LLM_COST_INPUT_USD_PER_1K": "input price",
    "GIGMATE_LLM_COST_OUTPUT_USD_PER_1K": "output price",
    "GIGMATE_LLM_MAX_INPUT_TOKENS": "input token cap",
    "GIGMATE_LLM_MAX_OUTPUT_TOKENS": "output token cap",
    "GIGMATE_LLM_DAILY_CALL_BUDGET": "daily call ceiling",
    "GIGMATE_LLM_DAILY_TOKEN_BUDGET": "daily token ceiling",
    "GIGMATE_WORKSPACE_TIMEZONE": "time basis for relative dates",
    "GIGMATE_MEDIA_ENABLED": "media seam switch",
    "GIGMATE_MEDIA_LIVE": "media live gate",
    "GIGMATE_MEDIA_API_KEY": "media credential (value never printed)",
    "GIGMATE_MEDIA_MODALITIES": "authorized media modalities",
    "GIGMATE_MEDIA_VISION_VENDORS": "verified vision vendors",
}


# A live text deployment cannot start without these; everything else has a
# built-in default (price list, token caps) or belongs to a seam that stays
# closed unless the operator opens it (media).
REQUIRED_VARS = frozenset(
    {
        "GIGMATE_LLM_PROVIDER",
        "GIGMATE_LLM_MODEL",
        "GIGMATE_LLM_API_KEY",
        "GIGMATE_LLM_LIVE",
    }
)


def build_report() -> dict[str, object]:
    text = LLMProvider()
    # A credential may arrive as a file (``<NAME>_FILE``) instead of a value;
    # presence is what matters here and the value is still never printed.
    present = {
        name: (
            "set"
            if (
                secrets.configured(name)
                if name.endswith("_API_KEY")
                else os.environ.get(name)
            )
            else "missing"
        )
        for name in PRESENCE_VARS
    }
    config_problems = list(validate_provider_config() or [])
    refusal = text._refusal_reason(None)
    media = media_llm.env_summary()
    report = {
        "text": {
            "vendor": text._configured_provider,
            "model": text._configured_model,
            "live_gate": bool(text._configured_live),
            "live_origin_allowed": bool(text._allow_live_origin),
            "configured_for_live": not config_problems and refusal is None,
            "config_problems": config_problems,
            "refusal_reason": refusal[0] if refusal else None,
        },
        "media": {
            "seam_enabled": media_llm.is_seam_enabled(),
            "live_gate": media_llm.is_live_unlocked(),
            "modalities": sorted(media_llm.authorized_modalities()),
            "vision_vendors": sorted(media_llm.vision_vendors()),
            "audio_vendor": media.get("audio_vendor") or None,
        },
        "presence": present,
        "missing_required": sorted(
            name
            for name, state in present.items()
            if state == "missing" and name in REQUIRED_VARS
        ),
        "missing_optional": sorted(
            name
            for name, state in present.items()
            if state == "missing" and name not in REQUIRED_VARS
        ),
    }
    ready = (
        report["text"]["configured_for_live"]  # type: ignore[index]
        and not report["missing_required"]  # type: ignore[operator]
    )
    report["configuration_complete"] = bool(ready)
    report["note"] = (
        "Configuration completeness only. Vendor quality, real price, latency "
        "and any real customer run are separate, evidenced acceptances."
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit the report as JSON.")
    args = parser.parse_args()

    report = build_report()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        text = report["text"]  # type: ignore[assignment]
        media = report["media"]  # type: ignore[assignment]
        print("text vendor        :", text["vendor"] or "-")  # type: ignore[index]
        print("text model         :", text["model"] or "-")  # type: ignore[index]
        print("live gate          :", text["live_gate"])  # type: ignore[index]
        print("live origin        :", text["live_origin_allowed"])  # type: ignore[index]
        print("configured for live:", text["configured_for_live"])  # type: ignore[index]
        if text["refusal_reason"]:  # type: ignore[index]
            print("refusal reason     :", text["refusal_reason"])  # type: ignore[index]
        print("media seam         :", media["seam_enabled"])  # type: ignore[index]
        print("media modalities   :", ",".join(media["modalities"]) or "-")  # type: ignore[index]
        print("vision vendors     :", ",".join(media["vision_vendors"]) or "-")  # type: ignore[index]
        print(
            "missing (required) :",
            ", ".join(report["missing_required"]) or "none",  # type: ignore[index]
        )
        print(
            "missing (optional) :",
            ", ".join(report["missing_optional"]) or "none",  # type: ignore[index]
        )
        print("configuration complete:", report["configuration_complete"])  # type: ignore[index]
        print(report["note"])  # type: ignore[index]
    return 0 if report["configuration_complete"] else 1  # type: ignore[index]


if __name__ == "__main__":
    raise SystemExit(main())
