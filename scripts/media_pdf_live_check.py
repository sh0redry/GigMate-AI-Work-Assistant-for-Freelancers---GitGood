"""Real end-to-end PDF check against a configured vendor.

The PDF path needs the Linux-only parser isolation sandbox
(:mod:`gigmate.media.pdf_child` uses resource limits that macOS cannot
provide), so on a developer Mac this script reports the platform limit instead
of pretending. Run it inside a Linux container to get real evidence:

.. code-block:: text

    docker run --rm -v "$PWD":/work -w /work python:3.12-slim \\
        bash -c "pip install -q -r /work/apps/backend/requirements.lock && \\
        python /work/scripts/media_pdf_live_check.py"

with ``GIGMATE_MEDIA_ENABLED=1``, ``GIGMATE_MEDIA_MODALITIES=pdf`` and the
vendor variables in the environment. The script costs a real call and refuses
to run unless the live gate is open, so it is safe to keep around.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "apps",
        "backend",
        "src",
    ),
)

from gigmate.media import pdfparse  # noqa: E402
from gigmate.media.processor import MediaProcessorImpl  # noqa: E402
from gigmate.media_processing import MediaInput  # noqa: E402
from gigmate.errors import BusinessError  # noqa: E402

TEXT = "Deliver the parcel by TUE 3PM."


def synthetic_pdf() -> bytes:
    """A one-page PDF whose single text line is :data:`TEXT`.

    Built by hand so the check has no extra dependency: an uncompressed
    content stream that any conforming parser can read back verbatim.
    """

    stream = f"BT /F1 14 Tf 40 700 Td ({TEXT}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length "
        + str(len(stream)).encode()
        + b" >>\nstream\n"
        + stream
        + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def main() -> int:
    content = synthetic_pdf()
    if os.environ.get("GIGMATE_MEDIA_ENABLED") != "1":
        print("REFUSED: GIGMATE_MEDIA_ENABLED is not 1; this check costs a real call.")
        return 2
    try:
        extraction = pdfparse.extract(content)
        parser = [page.text for page in extraction.pages]
    except Exception as exc:  # noqa: BLE001 - reported, not swallowed
        print(f"PDF PARSER UNAVAILABLE: {type(exc).__name__}: {exc}")
        print("(the parser sandbox is Linux-only; run this inside a Linux container)")
        return 3

    media_input = MediaInput(
        request_id="req-pdf-live",
        account_id="acct-pdf-live",
        conversation_id="conv-pdf-live",
        snapshot_id="snap-pdf-live",
        attachment_id="att-pdf-live",
        attachment_version=1,
        context_version=0,
        source_fingerprint="fp-pdf-live",
        sha256=hashlib.sha256(content).hexdigest(),
        mimetype="application/pdf",
        source_occurred_at="2026-10-10T00:00:00Z",
        content=content,
        caption="synthetic one-page PDF",
        origin="live",
    )
    try:
        result = MediaProcessorImpl().process(media_input)
    except BusinessError as exc:
        print(f"REFUSED: {exc.code}: {exc.message}")
        return 4
    print(
        json.dumps(
            {
                "parser_pages": parser,
                "segments": [segment.text for segment in result.segments],
                "coverage": getattr(result.coverage, "value", result.coverage),
                "model_version": result.model_version,
                "prompt_version": result.prompt_version,
                "unresolved": [
                    getattr(q, "text", None)
                    or (q.get("text") if isinstance(q, dict) else str(q))
                    for q in (result.unresolved_questions or [])
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
