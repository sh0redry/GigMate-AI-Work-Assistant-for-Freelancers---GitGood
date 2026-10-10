#!/usr/bin/env python
"""Operator-side manual smoke for the WAHA media processor (Role B).

This script is **not** part of CI. It exists so a human operator can verify
that an end-to-end media call returns a parseable proposal once the seam
flag and operator switch are open.

Usage:

.. code-block:: bash

    .venv/bin/python scripts/smoke_media.py --mime image/png --file path/to/sample.png
    .venv/bin/python scripts/smoke_media.py --mime audio/ogg --file path/to/sample.ogg

Required environment variables (all must be set for a real call):

* ``GIGMATE_MEDIA_PROCESSOR_FACTORY=gigmate.media.processor:MediaProcessorImpl``
* ``GIGMATE_MEDIA_LIVE=1``
* ``GIGMATE_MEDIA_API_KEY=<vendor key>``
* ``GIGMATE_MEDIA_ALLOW_LIVE_ORIGIN=1`` (when sending a real attachment)

The seam flag in ``gigmate.media.processor`` defaults to ``False``. The
operator must flip that flag in the source before this script will actually
call the vendor. This double-key design is intentional; see
``docs/en/role-b-extraction.md`` for the rationale.

Without the seam flag the script prints the refusal reason and exits with
``1``; unavailable and uncertain outcomes are smoke failures.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Make the backend package importable when this script is invoked directly
# from a fresh checkout (no editable install). Keep at module scope so any
# subsequent import can resolve; ruff: noqa: E402.
sys.path.insert(0, str(REPO_ROOT / "apps" / "backend" / "src"))  # noqa: E402

from gigmate.media import llm  # noqa: E402
from gigmate.media.processor import MediaProcessorImpl, is_seam_enabled  # noqa: E402
from gigmate.media_processing import (  # noqa: E402
    MediaInput,
    ProcessingUnavailable,
    ProcessingUncertain,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mime", required=True, help="MIME type of the attachment")
    parser.add_argument(
        "--file", required=True, type=Path, help="Path to the attachment bytes"
    )
    parser.add_argument(
        "--origin",
        default="synthetic",
        choices=("synthetic", "live"),
        help="Origin marker (synthetic skips the live-origin gate)",
    )
    parser.add_argument(
        "--caption",
        default=None,
        help="Optional caption forwarded to the model as user context",
    )
    parser.add_argument(
        "--request-id",
        default="smoke-media",
        help="Local request id (vendor lookup is not implemented)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print("Media processor smoke")
    print("=====================")
    print(f"  seam flag enabled: {is_seam_enabled()}")
    print(f"  env summary: {json.dumps(llm.env_summary(), indent=2)}")

    if not args.file.exists():
        print(f"ERROR: file not found: {args.file}")
        return 2

    content = args.file.read_bytes()
    request = MediaInput(
        request_id=args.request_id,
        account_id="smoke-account",
        conversation_id="smoke-conversation",
        snapshot_id="smoke-snapshot",
        attachment_id="smoke-attachment",
        attachment_version=1,
        context_version=0,
        source_fingerprint="smoke",
        sha256=hashlib.sha256(content).hexdigest(),
        mimetype=args.mime,
        source_occurred_at="2026-10-10T00:00:00Z",
        content=content,
        caption=args.caption,
        origin=args.origin,
    )
    proc = MediaProcessorImpl()
    try:
        result = proc.process(request)
    except ProcessingUnavailable as exc:
        print(f"\nRefused (unavailable): {exc}")
        return 1
    except ProcessingUncertain as exc:
        print(f"\nRefused (uncertain — reconcile): {exc}")
        return 1

    print("\nProposal")
    print("--------")
    payload = result.model_dump(mode="json")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    # Refuse to run if the operator has not set the factory.
    factory = os.environ.get("GIGMATE_MEDIA_PROCESSOR_FACTORY", "")
    if factory and factory != "gigmate.media.processor:MediaProcessorImpl":
        print(
            f"NOTE: GIGMATE_MEDIA_PROCESSOR_FACTORY={factory!r} is set; this "
            "smoke always calls MediaProcessorImpl directly. Unset the env "
            "var if you want the smoke to honour your override."
        )
    sys.exit(main())
