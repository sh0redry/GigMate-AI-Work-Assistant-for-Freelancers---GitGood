"""Real-model media processor tests (Role B seam).

The processor is loaded via ``gigmate.media_processing.processor`` once the
operator sets ``GIGMATE_MEDIA_PROCESSOR_FACTORY=gigmate.media.processor:MediaProcessorImpl``.
These tests exercise the implementation directly with a fake ``httpx.Client``
to keep the suite hermetic; they do not contact any vendor.

Coverage:

* Two-gate safety: seam flag, operator switch, API key, live-origin gate.
* Routing: PNG / JPEG / WebP -> ocr, Ogg / MP3 / WAV / M4A -> asr, PDF -> pdf,
  plain text -> text, anything else -> ProcessingUnavailable.
* Per-vendor call shape: chat-completions request URL/payload, transcription
  multipart request body.
* PDF pipeline: local per-page parse is the source of truth (the model cannot
  retype segments); parse refusals (no text layer, garbage bytes, page bound)
  happen before any vendor call; long pages split into bounded chunks; blank
  pages surface an unresolved question; vendor 5xx after a successful parse
  is ProcessingUncertain.
* Coercion: vendor JSON -> WahaMediaResult with valid bounds.
* Failure modes: 4xx / 5xx -> ProcessingUncertain, network error ->
  ProcessingUncertain, malformed vendor JSON -> ProcessingUncertain.
* Security boundary: ``MediaInput`` carries no ``api_key``/``provider_url``;
  ``MediaInput`` is not mutated by the processor.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import sys
from typing import Any

import httpx
import pytest
from pypdf import PdfWriter

import gigmate.media.llm as llm
import gigmate.media.processor as mp
from gigmate.contracts import WahaMediaResult
from gigmate.media.coercion import coerce_chat_response, coerce_transcription_response
from gigmate.media.processor import _ENABLED, MediaProcessorImpl, build_processor
from gigmate.media_processing import MediaInput, ProcessingUnavailable, ProcessingUncertain

LINUX_PDF_ONLY = pytest.mark.skipif(
    sys.platform != "linux",
    reason="PDF child isolation needs Linux RLIMIT_AS/prctl; elsewhere the seam refuses with MEDIA_PDF_LIMIT_UNAVAILABLE",
)

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aA4sAAAAASUVORK5CYII="
)


# ------------------------------------------------------------ fixtures


@pytest.fixture
def saved_seam_flag():
    """Restore the seam flag after each test, even if it crashes."""

    original = _ENABLED
    try:
        yield
    finally:
        mp._ENABLED = original


@pytest.fixture
def saved_env(monkeypatch):
    """Wipe media-related env vars and let each test opt back in."""

    for key in (
        "GIGMATE_MEDIA_LIVE",
        "GIGMATE_MEDIA_ALLOW_LIVE_ORIGIN",
        "GIGMATE_MEDIA_API_KEY",
        "GIGMATE_MEDIA_ENDPOINT",
        "GIGMATE_MEDIA_CHAT_VENDOR",
        "GIGMATE_MEDIA_CHAT_MODEL",
        "GIGMATE_MEDIA_AUDIO_VENDOR",
        "GIGMATE_MEDIA_AUDIO_MODEL",
        "GIGMATE_MEDIA_PROMPT_PATH",
        "GIGMATE_MEDIA_MODALITIES",
        "GIGMATE_MEDIA_VISION_VENDORS",
    ):
        monkeypatch.delenv(key, raising=False)
    # Per-modality authorization and vision-vendor verification are asserted
    # by their own tests; the remaining cases opt in explicitly so they keep
    # exercising routing / call shape rather than the authorization gate.
    monkeypatch.setenv("GIGMATE_MEDIA_MODALITIES", "ocr,asr,pdf,text")
    monkeypatch.setenv("GIGMATE_MEDIA_VISION_VENDORS", "openai")
    # Audio is only reachable with its own named vendor; without it the
    # processor refuses instead of posting the chat key to a default ASR
    # endpoint (asserted by test_audio_vendor_must_be_named).
    monkeypatch.setenv("GIGMATE_MEDIA_AUDIO_VENDOR", "openai")
    monkeypatch.setenv("GIGMATE_MEDIA_AUDIO_MODEL", "whisper-1")
    yield monkeypatch


def make_input(
    mimetype: str = "image/png", content: bytes = PNG, origin: str = "live"
) -> MediaInput:
    return MediaInput(
        request_id="req-test",
        account_id="acct-test",
        conversation_id="conv-test",
        snapshot_id="snap-test",
        attachment_id="att-test",
        attachment_version=1,
        context_version=0,
        source_fingerprint="fp-test",
        sha256=hashlib.sha256(content).hexdigest(),
        mimetype=mimetype,
        source_occurred_at="2026-10-10T00:00:00Z",
        content=content,
        caption="synthetic caption",
        origin=origin,
    )


# Two-gate safety


def test_default_seam_flag_stays_locked(saved_env, saved_seam_flag):
    """The seam ships locked until real media acceptance is recorded.

    The adapters and the per-modality gates exist, but unlocking is a separate,
    evidenced step: with ``_ENABLED`` False the processor refuses before it
    reads any environment variable, so deploying this code (even with the live
    switch and every modality exported) cannot start sending attachments.
    """

    assert _ENABLED is False
    assert isinstance(build_processor(), MediaProcessorImpl)
    saved_env.setenv("GIGMATE_MEDIA_LIVE", "1")
    saved_env.setenv("GIGMATE_MEDIA_API_KEY", "synthetic-key")
    saved_env.setenv("GIGMATE_MEDIA_MODALITIES", "ocr,asr,pdf,text")
    with pytest.raises(ProcessingUnavailable, match="_ENABLED"):
        MediaProcessorImpl().process(make_input())


def test_seam_flag_off_still_refuses(saved_env, saved_seam_flag):
    """Flipping ``_ENABLED`` back to False keeps refusing before any env read."""

    mp._ENABLED = False
    saved_env.setenv("GIGMATE_MEDIA_LIVE", "1")
    saved_env.setenv("GIGMATE_MEDIA_API_KEY", "test-key")
    saved_env.setenv("GIGMATE_MEDIA_CHAT_VENDOR", "openai")
    with pytest.raises(ProcessingUnavailable, match="_ENABLED"):
        MediaProcessorImpl().process(make_input())


def test_seam_flag_without_live_switch_refuses(saved_env, saved_seam_flag):
    mp._ENABLED = True
    saved_env.setenv("GIGMATE_MEDIA_API_KEY", "test-key")
    saved_env.setenv("GIGMATE_MEDIA_ALLOW_LIVE_ORIGIN", "1")
    saved_env.setenv("GIGMATE_MEDIA_CHAT_VENDOR", "openai")
    with pytest.raises(ProcessingUnavailable, match="GIGMATE_MEDIA_LIVE"):
        MediaProcessorImpl().process(make_input())


def test_live_switch_without_key_refuses(saved_env, saved_seam_flag):
    mp._ENABLED = True
    saved_env.setenv("GIGMATE_MEDIA_LIVE", "1")
    saved_env.setenv("GIGMATE_MEDIA_ALLOW_LIVE_ORIGIN", "1")
    saved_env.setenv("GIGMATE_MEDIA_CHAT_VENDOR", "openai")
    with pytest.raises(ProcessingUnavailable, match="GIGMATE_MEDIA_API_KEY"):
        MediaProcessorImpl().process(make_input())


def test_live_origin_refused_by_default(saved_env, saved_seam_flag):
    mp._ENABLED = True
    saved_env.setenv("GIGMATE_MEDIA_LIVE", "1")
    saved_env.setenv("GIGMATE_MEDIA_API_KEY", "test-key")
    with pytest.raises(ProcessingUnavailable, match="Live-origin media is refused"):
        MediaProcessorImpl().process(make_input(origin="live"))


def test_modality_must_be_explicitly_authorized(saved_env, saved_seam_flag):
    """Opening the live switch does not authorize any specific modality."""
    mp._ENABLED = True
    saved_env.delenv("GIGMATE_MEDIA_MODALITIES", raising=False)
    saved_env.setenv("GIGMATE_MEDIA_LIVE", "1")
    saved_env.setenv("GIGMATE_MEDIA_API_KEY", "test-key")
    saved_env.setenv("GIGMATE_MEDIA_ALLOW_LIVE_ORIGIN", "1")
    saved_env.setenv("GIGMATE_MEDIA_CHAT_VENDOR", "openai")
    saved_env.setattr(llm, "default_client_factory", lambda **kwargs: pytest.fail("client built"))
    with pytest.raises(ProcessingUnavailable, match="MEDIA_MODALITY_NOT_AUTHORIZED"):
        MediaProcessorImpl().process(make_input())


def test_ocr_requires_a_verified_vision_vendor(saved_env, saved_seam_flag):
    """A chat vendor is not assumed to accept images without verification."""
    mp._ENABLED = True
    saved_env.setenv("GIGMATE_MEDIA_MODALITIES", "ocr")
    saved_env.delenv("GIGMATE_MEDIA_VISION_VENDORS", raising=False)
    saved_env.setenv("GIGMATE_MEDIA_LIVE", "1")
    saved_env.setenv("GIGMATE_MEDIA_API_KEY", "test-key")
    saved_env.setenv("GIGMATE_MEDIA_ALLOW_LIVE_ORIGIN", "1")
    saved_env.setenv("GIGMATE_MEDIA_CHAT_VENDOR", "openai")
    saved_env.setattr(llm, "default_client_factory", lambda **kwargs: pytest.fail("client built"))
    with pytest.raises(ProcessingUnavailable, match="MEDIA_VISION_VENDOR_UNVERIFIED"):
        MediaProcessorImpl().process(make_input())


def test_deepseek_is_never_assumed_to_accept_images(saved_env, saved_seam_flag):
    """Verifying one vendor must not implicitly verify another."""
    mp._ENABLED = True
    saved_env.setenv("GIGMATE_MEDIA_MODALITIES", "ocr")
    saved_env.setenv("GIGMATE_MEDIA_VISION_VENDORS", "openai")
    saved_env.setenv("GIGMATE_MEDIA_LIVE", "1")
    saved_env.setenv("GIGMATE_MEDIA_API_KEY", "test-key")
    saved_env.setenv("GIGMATE_MEDIA_ALLOW_LIVE_ORIGIN", "1")
    saved_env.setenv("GIGMATE_MEDIA_CHAT_VENDOR", "deepseek")
    saved_env.setattr(llm, "default_client_factory", lambda **kwargs: pytest.fail("client built"))
    with pytest.raises(ProcessingUnavailable, match="MEDIA_VISION_VENDOR_UNVERIFIED"):
        MediaProcessorImpl().process(make_input())


@LINUX_PDF_ONLY
def test_pdf_modality_requires_its_own_authorization(saved_env, saved_seam_flag):
    """Authorizing OCR alone must not enable document shipping."""
    mp._ENABLED = True
    saved_env.setenv("GIGMATE_MEDIA_MODALITIES", "ocr")
    saved_env.setenv("GIGMATE_MEDIA_LIVE", "1")
    saved_env.setenv("GIGMATE_MEDIA_API_KEY", "test-key")
    saved_env.setenv("GIGMATE_MEDIA_ALLOW_LIVE_ORIGIN", "1")
    saved_env.setenv("GIGMATE_MEDIA_CHAT_VENDOR", "openai")
    with pytest.raises(ProcessingUnavailable, match="MEDIA_MODALITY_NOT_AUTHORIZED: pdf"):
        MediaProcessorImpl().process(make_input(mimetype="application/pdf", content=b"%PDF-1"))


def test_unknown_origin_passes_origin_check(saved_env, saved_seam_flag):
    mp._ENABLED = True
    saved_env.setenv("GIGMATE_MEDIA_LIVE", "1")
    saved_env.setenv("GIGMATE_MEDIA_API_KEY", "test-key")
    saved_env.setenv("GIGMATE_MEDIA_CHAT_VENDOR", "openai")
    # synthetic origin does not require the explicit live-origin opt-in
    fake_client = _FakeClient(chat_payload=_chat_ok())
    saved_env.setattr(llm, "default_client_factory", lambda *, timeout: fake_client)
    result = MediaProcessorImpl().process(make_input(origin="synthetic"))
    assert isinstance(result, WahaMediaResult)


def test_unknown_vendor_refuses(saved_env, saved_seam_flag):
    mp._ENABLED = True
    saved_env.setenv("GIGMATE_MEDIA_LIVE", "1")
    saved_env.setenv("GIGMATE_MEDIA_API_KEY", "test-key")
    saved_env.setenv("GIGMATE_MEDIA_ALLOW_LIVE_ORIGIN", "1")
    saved_env.setenv("GIGMATE_MEDIA_CHAT_VENDOR", "openai")
    saved_env.setenv("GIGMATE_MEDIA_CHAT_VENDOR", "unknown-vendor")
    with pytest.raises(ProcessingUnavailable, match="Unknown chat vendor"):
        MediaProcessorImpl().process(make_input())


def test_unsupported_mime_refuses(saved_env, saved_seam_flag):
    mp._ENABLED = True
    saved_env.setenv("GIGMATE_MEDIA_LIVE", "1")
    saved_env.setenv("GIGMATE_MEDIA_API_KEY", "test-key")
    saved_env.setenv("GIGMATE_MEDIA_ALLOW_LIVE_ORIGIN", "1")
    saved_env.setenv("GIGMATE_MEDIA_CHAT_VENDOR", "openai")
    with pytest.raises(ProcessingUnavailable, match="not accepted"):
        MediaProcessorImpl().process(make_input(mimetype="image/gif"))


# Per-MIME routing


@pytest.mark.parametrize(
    "mimetype,dispatch",
    [
        ("image/png", "ocr"),
        ("image/jpeg", "ocr"),
        ("image/webp", "ocr"),
        ("audio/ogg", "asr"),
        ("audio/mpeg", "asr"),
        ("audio/wav", "asr"),
        ("audio/mp4", "asr"),
        ("audio/x-m4a", "asr"),
        ("application/pdf", "pdf"),
        ("text/plain", "text"),
    ],
)
def test_routing_dispatch(saved_env, monkeypatch, mimetype, dispatch):
    from gigmate.media.routing import route

    assert route(mimetype) == dispatch


@pytest.mark.parametrize(
    "mimetype,factory",
    [
        ("image/png", "_chat_ok"),
        ("image/jpeg", "_chat_ok"),
        ("image/webp", "_chat_ok"),
        ("text/plain", "_chat_ok"),
        ("audio/ogg", "_transcription_ok"),
        ("audio/mpeg", "_transcription_ok"),
        ("audio/wav", "_transcription_ok"),
        ("audio/x-m4a", "_transcription_ok"),
    ],
)
def test_per_mime_call_shape(saved_env, saved_seam_flag, mimetype, factory):
    mp._ENABLED = True
    saved_env.setenv("GIGMATE_MEDIA_LIVE", "1")
    saved_env.setenv("GIGMATE_MEDIA_API_KEY", "test-key")
    saved_env.setenv("GIGMATE_MEDIA_ALLOW_LIVE_ORIGIN", "1")
    saved_env.setenv("GIGMATE_MEDIA_CHAT_VENDOR", "openai")
    payload = globals()[factory]()
    fake = (
        _FakeClient(chat_payload=payload)
        if factory == "_chat_ok"
        else _FakeClient(transcription_payload=payload)
    )
    saved_env.setattr(llm, "default_client_factory", lambda *, timeout: fake)
    result = MediaProcessorImpl().process(
        make_input(
            mimetype=mimetype, content=b"synthetic text" if mimetype == "text/plain" else PNG
        )
    )
    assert isinstance(result, WahaMediaResult)
    assert fake.calls
    assert result.coverage in {"complete", "partial", "unknown"}


# Coercion


def _chat_ok() -> dict[str, Any]:
    return {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "coverage": "complete",
                            "segments": [
                                {
                                    "text": "Synthetic OCR text",
                                    "page": None,
                                    "start_ms": None,
                                    "end_ms": None,
                                }
                            ],
                            "summary": "Synthetic summary",
                            "suggestions": [
                                {
                                    "field": "requirements",
                                    "text": "Synthetic requirement",
                                    "source_indices": [0],
                                }
                            ],
                            "unresolved_questions": [],
                        }
                    )
                }
            }
        ]
    }


def _transcription_ok() -> dict[str, Any]:
    return {
        "text": "Synthetic transcript",
        "segments": [
            {"id": 0, "start": 0.0, "end": 1.5, "text": "Synthetic transcript"},
        ],
    }


def test_chat_coercion_validates_bounds():
    payload = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "coverage": "partial",
                            "segments": [
                                {"text": "hello", "start_ms": 0, "end_ms": 1000},
                                {"text": "world", "start_ms": 1000, "end_ms": 2500},
                            ],
                            "suggestions": [
                                {"field": "schedule", "text": "next monday", "source_indices": [0]},
                                {"field": "address", "text": "main st", "source_indices": [1]},
                            ],
                            "unresolved_questions": ["caption missing"],
                        }
                    )
                }
            }
        ]
    }
    result = coerce_chat_response(
        payload, prompt_version="1.0.0", vendor="media-llm", model_version="deepseek:deepseek-chat"
    )
    assert result.provider == "media-llm"
    assert result.model_version == "deepseek:deepseek-chat"
    assert result.prompt_version == "1.0.0"
    assert len(result.segments) == 2
    assert result.segments[0].start_ms == 0 and result.segments[1].end_ms == 2500


def test_chat_coercion_rejects_out_of_bounds_source_indices():
    payload = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "coverage": "complete",
                            "segments": [{"text": "hello"}],
                            "suggestions": [
                                {"field": "schedule", "text": "next monday", "source_indices": [5]}
                            ],
                        }
                    )
                }
            }
        ]
    }
    with pytest.raises(ProcessingUncertain, match="validation"):
        coerce_chat_response(
            payload,
            prompt_version="1.0.0",
            vendor="media-llm",
            model_version="deepseek:deepseek-chat",
        )


def test_chat_coercion_rejects_non_json_message():
    payload = {"choices": [{"message": {"content": "not json"}}]}
    with pytest.raises(ProcessingUncertain):
        coerce_chat_response(
            payload,
            prompt_version="1.0.0",
            vendor="media-llm",
            model_version="deepseek:deepseek-chat",
        )


def test_chat_coercion_rejects_missing_choices():
    with pytest.raises(ProcessingUncertain):
        coerce_chat_response(
            {}, prompt_version="1.0.0", vendor="media-llm", model_version="deepseek:deepseek-chat"
        )


def test_transcription_coercion_builds_segments():
    payload = {
        "text": "Synthetic transcript",
        "segments": [
            {"id": 0, "start": 0.0, "end": 1.5, "text": "Synthetic transcript"},
        ],
    }
    result = coerce_transcription_response(
        payload, prompt_version="1.0.0", vendor="media-llm", model_version="openai:whisper-1"
    )
    assert result.model_version == "openai:whisper-1"
    assert result.segments
    assert result.segments[0].start_ms == 0
    assert result.segments[0].end_ms == 1500


def test_transcription_coercion_rejects_empty_text():
    with pytest.raises(ProcessingUncertain, match="no text"):
        coerce_transcription_response(
            {"text": ""},
            prompt_version="1.0.0",
            vendor="media-llm",
            model_version="openai:whisper-1",
        )


# Failure modes


def test_5xx_is_uncertain(saved_env, saved_seam_flag):
    mp._ENABLED = True
    saved_env.setenv("GIGMATE_MEDIA_LIVE", "1")
    saved_env.setenv("GIGMATE_MEDIA_API_KEY", "test-key")
    saved_env.setenv("GIGMATE_MEDIA_ALLOW_LIVE_ORIGIN", "1")
    saved_env.setenv("GIGMATE_MEDIA_CHAT_VENDOR", "openai")
    fake = _FakeClient(status_code=500, body=b'{"error":"server"}')
    saved_env.setattr(llm, "default_client_factory", lambda *, timeout: fake)
    with pytest.raises(ProcessingUncertain, match="MEDIA_VENDOR_REJECTED"):
        MediaProcessorImpl().process(make_input())


def test_4xx_is_uncertain(saved_env, saved_seam_flag):
    mp._ENABLED = True
    saved_env.setenv("GIGMATE_MEDIA_LIVE", "1")
    saved_env.setenv("GIGMATE_MEDIA_API_KEY", "test-key")
    saved_env.setenv("GIGMATE_MEDIA_ALLOW_LIVE_ORIGIN", "1")
    saved_env.setenv("GIGMATE_MEDIA_CHAT_VENDOR", "openai")
    fake = _FakeClient(status_code=400, body=b'{"error":"bad request"}')
    saved_env.setattr(llm, "default_client_factory", lambda *, timeout: fake)
    with pytest.raises(ProcessingUncertain, match="MEDIA_VENDOR_REJECTED"):
        MediaProcessorImpl().process(make_input())


def test_network_error_is_uncertain(saved_env, saved_seam_flag):
    mp._ENABLED = True
    saved_env.setenv("GIGMATE_MEDIA_LIVE", "1")
    saved_env.setenv("GIGMATE_MEDIA_API_KEY", "test-key")
    saved_env.setenv("GIGMATE_MEDIA_ALLOW_LIVE_ORIGIN", "1")
    saved_env.setenv("GIGMATE_MEDIA_CHAT_VENDOR", "openai")
    fake = _FakeClient(raise_network=True)
    saved_env.setattr(llm, "default_client_factory", lambda *, timeout: fake)
    with pytest.raises(ProcessingUncertain, match="MEDIA_VENDOR_RESULT_UNKNOWN"):
        MediaProcessorImpl().process(make_input())


def test_malformed_json_is_uncertain(saved_env, saved_seam_flag):
    mp._ENABLED = True
    saved_env.setenv("GIGMATE_MEDIA_LIVE", "1")
    saved_env.setenv("GIGMATE_MEDIA_API_KEY", "test-key")
    saved_env.setenv("GIGMATE_MEDIA_ALLOW_LIVE_ORIGIN", "1")
    saved_env.setenv("GIGMATE_MEDIA_CHAT_VENDOR", "openai")
    fake = _FakeClient(chat_payload=None, body=b"not json")
    saved_env.setattr(llm, "default_client_factory", lambda *, timeout: fake)
    with pytest.raises(ProcessingUncertain, match="MEDIA_VENDOR_REJECTED"):
        MediaProcessorImpl().process(make_input())


# PDF pipeline (local parse -> business extraction)


def _build_pdf(*page_texts: str) -> bytes:
    """Build a minimal but structurally valid PDF, one page per text.

    Hand-assembling the objects (catalog, pages, font, page + content
    streams, xref, trailer) keeps the helper dependency-free and
    deterministic: ``pypdf`` extracts exactly the text we place in the
    ``Tj`` operator, which is what the parser tests assert against.
    """

    objects: list[bytes] = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    count = len(page_texts)
    kids = " ".join(f"{4 + i * 2} 0 R" for i in range(count))
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {count} >>".encode())
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for index, text in enumerate(page_texts):
        content_num = 5 + index * 2
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_num} 0 R >>".encode()
        )
        safe = text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
        stream = f"BT /F1 12 Tf 72 700 Td ({safe}) Tj ET".encode("latin-1", "replace")
        objects.append(
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
        )
    out = bytearray(b"%PDF-1.7\n")
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF"
    ).encode()
    return bytes(out)


def _blank_pdf(pages: int) -> bytes:
    """Build a valid PDF whose pages carry no text layer (scanned shape)."""

    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=100, height=100)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _pdf_ok() -> dict[str, Any]:
    """Vendor body for the PDF business-extraction pass.

    Note the deliberate fake ``segments`` key: the model must not be able
    to retype page text, so the coercion ignores it and keeps the locally
    parsed segments.
    """

    return {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "coverage": "complete",
                            "segments": [
                                {"text": "MODEL INJECTED TEXT", "page": 9},
                            ],
                            "summary": "A two-page work brief",
                            "suggestions": [
                                {
                                    "field": "requirements",
                                    "text": "bring own tools",
                                    "source_indices": [0],
                                }
                            ],
                            "unresolved_questions": [],
                        }
                    )
                }
            }
        ]
    }


@LINUX_PDF_ONLY
def test_pdf_real_parse_and_extraction(saved_env, saved_seam_flag):
    """Two-layer pipeline: local page text is the source of truth; the
    model only contributes the business layer and cannot retype
    segments."""

    mp._ENABLED = True
    saved_env.setenv("GIGMATE_MEDIA_LIVE", "1")
    saved_env.setenv("GIGMATE_MEDIA_API_KEY", "test-key")
    saved_env.setenv("GIGMATE_MEDIA_ALLOW_LIVE_ORIGIN", "1")
    saved_env.setenv("GIGMATE_MEDIA_CHAT_VENDOR", "openai")
    fake = _FakeClient(chat_payload=_pdf_ok())
    saved_env.setattr(llm, "default_client_factory", lambda *, timeout: fake)
    content = _build_pdf("First page quote text", "Second page quote text")
    result = MediaProcessorImpl().process(make_input(mimetype="application/pdf", content=content))

    assert isinstance(result, WahaMediaResult)
    # Segments come from the local parser, verbatim, with page numbers.
    assert [(segment.page, segment.text) for segment in result.segments] == [
        (1, "First page quote text"),
        (2, "Second page quote text"),
    ]
    # The model's injected segments key was ignored.
    assert all("MODEL INJECTED" not in segment.text for segment in result.segments)
    assert result.coverage == "complete"
    assert result.summary == "A two-page work brief"
    assert [s.field for s in result.suggestions] == ["requirements"]
    assert result.suggestions[0].source_indices == [0]
    # One chat call whose user payload carries the extracted pages.
    assert len(fake.calls) == 1
    url, kwargs = fake.calls[0]
    assert url.endswith("/v1/chat/completions")
    user_content = kwargs["json"]["messages"][1]["content"]
    sent_text = user_content[-1]["text"]
    assert "First page quote text" in sent_text
    assert "Second page quote text" in sent_text


@LINUX_PDF_ONLY
def test_pdf_no_text_layer_refuses_without_vendor_call(saved_env, saved_seam_flag):
    mp._ENABLED = True
    saved_env.setenv("GIGMATE_MEDIA_LIVE", "1")
    saved_env.setenv("GIGMATE_MEDIA_API_KEY", "test-key")
    saved_env.setenv("GIGMATE_MEDIA_ALLOW_LIVE_ORIGIN", "1")
    saved_env.setenv("GIGMATE_MEDIA_CHAT_VENDOR", "openai")
    fake = _FakeClient(chat_payload=_pdf_ok())
    saved_env.setattr(llm, "default_client_factory", lambda *, timeout: fake)
    with pytest.raises(ProcessingUnavailable, match="MEDIA_PDF_NO_TEXT_LAYER"):
        MediaProcessorImpl().process(make_input(mimetype="application/pdf", content=_blank_pdf(1)))
    assert fake.calls == []


@LINUX_PDF_ONLY
def test_pdf_invalid_bytes_refuse_without_vendor_call(saved_env, saved_seam_flag):
    mp._ENABLED = True
    saved_env.setenv("GIGMATE_MEDIA_LIVE", "1")
    saved_env.setenv("GIGMATE_MEDIA_API_KEY", "test-key")
    saved_env.setenv("GIGMATE_MEDIA_ALLOW_LIVE_ORIGIN", "1")
    saved_env.setenv("GIGMATE_MEDIA_CHAT_VENDOR", "openai")
    fake = _FakeClient(chat_payload=_pdf_ok())
    saved_env.setattr(llm, "default_client_factory", lambda *, timeout: fake)
    with pytest.raises(ProcessingUnavailable, match="MEDIA_PDF_NOT_PARSEABLE"):
        MediaProcessorImpl().process(
            make_input(mimetype="application/pdf", content=b"definitely not a pdf")
        )
    assert fake.calls == []


@LINUX_PDF_ONLY
def test_pdf_page_limit_refuses(saved_env, saved_seam_flag):
    """The page bound is checked before any text is extracted: a 201-page
    file is refused with the page-limit code, not the no-text-layer code."""

    mp._ENABLED = True
    saved_env.setenv("GIGMATE_MEDIA_LIVE", "1")
    saved_env.setenv("GIGMATE_MEDIA_API_KEY", "test-key")
    saved_env.setenv("GIGMATE_MEDIA_ALLOW_LIVE_ORIGIN", "1")
    saved_env.setenv("GIGMATE_MEDIA_CHAT_VENDOR", "openai")
    fake = _FakeClient(chat_payload=_pdf_ok())
    saved_env.setattr(llm, "default_client_factory", lambda *, timeout: fake)
    with pytest.raises(ProcessingUnavailable, match="MEDIA_PDF_PAGE_LIMIT"):
        MediaProcessorImpl().process(
            make_input(mimetype="application/pdf", content=_blank_pdf(201))
        )
    assert fake.calls == []


@LINUX_PDF_ONLY
def test_pdf_long_page_splits_into_bounded_segments(saved_env, saved_seam_flag):
    mp._ENABLED = True
    saved_env.setenv("GIGMATE_MEDIA_LIVE", "1")
    saved_env.setenv("GIGMATE_MEDIA_API_KEY", "test-key")
    saved_env.setenv("GIGMATE_MEDIA_ALLOW_LIVE_ORIGIN", "1")
    saved_env.setenv("GIGMATE_MEDIA_CHAT_VENDOR", "openai")
    fake = _FakeClient(chat_payload=_pdf_ok())
    saved_env.setattr(llm, "default_client_factory", lambda *, timeout: fake)
    content = _build_pdf("x" * 9000)
    result = MediaProcessorImpl().process(make_input(mimetype="application/pdf", content=content))
    assert len(result.segments) == 3
    assert all(segment.page == 1 for segment in result.segments)
    assert all(len(segment.text) <= 4000 for segment in result.segments)
    assert "".join(segment.text for segment in result.segments) == "x" * 9000


@LINUX_PDF_ONLY
def test_pdf_blank_pages_surface_unresolved_question(saved_env, saved_seam_flag):
    """A partly scanned PDF keeps its readable pages but the result must
    say how many pages carried no text instead of claiming full
    coverage."""

    mp._ENABLED = True
    saved_env.setenv("GIGMATE_MEDIA_LIVE", "1")
    saved_env.setenv("GIGMATE_MEDIA_API_KEY", "test-key")
    saved_env.setenv("GIGMATE_MEDIA_ALLOW_LIVE_ORIGIN", "1")
    saved_env.setenv("GIGMATE_MEDIA_CHAT_VENDOR", "openai")
    fake = _FakeClient(chat_payload=_pdf_ok())
    saved_env.setattr(llm, "default_client_factory", lambda *, timeout: fake)
    content = _build_pdf("readable page", "")
    result = MediaProcessorImpl().process(make_input(mimetype="application/pdf", content=content))
    assert len(result.segments) == 1
    assert any("1 of 2 pages" in question for question in result.unresolved_questions)


@LINUX_PDF_ONLY
def test_pdf_vendor_5xx_is_uncertain(saved_env, saved_seam_flag):
    """Once the local parse succeeds and the vendor is contacted, a 5xx
    may have been charged and must be Uncertain, not Unavailable."""

    mp._ENABLED = True
    saved_env.setenv("GIGMATE_MEDIA_LIVE", "1")
    saved_env.setenv("GIGMATE_MEDIA_API_KEY", "test-key")
    saved_env.setenv("GIGMATE_MEDIA_ALLOW_LIVE_ORIGIN", "1")
    saved_env.setenv("GIGMATE_MEDIA_CHAT_VENDOR", "openai")
    fake = _FakeClient(status_code=500, body=b'{"error":"server"}')
    saved_env.setattr(llm, "default_client_factory", lambda *, timeout: fake)
    with pytest.raises(ProcessingUncertain, match="MEDIA_VENDOR_REJECTED"):
        MediaProcessorImpl().process(
            make_input(mimetype="application/pdf", content=_build_pdf("vendor fails later"))
        )


@LINUX_PDF_ONLY
def test_pdf_text_limit_refuses(saved_env, saved_seam_flag):
    """A document whose extracted text exceeds the contract's 100000-char
    bound is refused outright, never silently truncated."""

    mp._ENABLED = True
    saved_env.setenv("GIGMATE_MEDIA_LIVE", "1")
    saved_env.setenv("GIGMATE_MEDIA_API_KEY", "test-key")
    saved_env.setenv("GIGMATE_MEDIA_ALLOW_LIVE_ORIGIN", "1")
    saved_env.setenv("GIGMATE_MEDIA_CHAT_VENDOR", "openai")
    fake = _FakeClient(chat_payload=_pdf_ok())
    saved_env.setattr(llm, "default_client_factory", lambda *, timeout: fake)
    content = _build_pdf("y" * 100001)
    with pytest.raises(ProcessingUnavailable, match="MEDIA_PDF_TEXT_LIMIT"):
        MediaProcessorImpl().process(make_input(mimetype="application/pdf", content=content))
    assert fake.calls == []


@LINUX_PDF_ONLY
def test_pdf_oversized_document_refuses_on_text_bound(saved_env, saved_seam_flag):
    """Bound precedence: an oversized multi-page document hits the
    total-text bound before the split can overflow the segment bound,
    and the refusal is explicit rather than a silent truncation."""

    mp._ENABLED = True
    saved_env.setenv("GIGMATE_MEDIA_LIVE", "1")
    saved_env.setenv("GIGMATE_MEDIA_API_KEY", "test-key")
    saved_env.setenv("GIGMATE_MEDIA_ALLOW_LIVE_ORIGIN", "1")
    saved_env.setenv("GIGMATE_MEDIA_CHAT_VENDOR", "openai")
    fake = _FakeClient(chat_payload=_pdf_ok())
    saved_env.setattr(llm, "default_client_factory", lambda *, timeout: fake)
    # 101 pages x 9000 chars = 909000 chars total: far past the 100000-char
    # contract bound, so the parser refuses on total text before any
    # vendor call. (The segment bound stays defensive behind it: >200
    # chunks of <=4000 chars always implies >100000 chars of text.)
    content = _build_pdf(*(["z" * 9000] * 101))
    with pytest.raises(ProcessingUnavailable, match="MEDIA_PDF_TEXT_LIMIT"):
        MediaProcessorImpl().process(make_input(mimetype="application/pdf", content=content))
    assert fake.calls == []


@LINUX_PDF_ONLY
def test_pdf_model_bad_source_indices_is_uncertain(saved_env, saved_seam_flag):
    mp._ENABLED = True
    saved_env.setenv("GIGMATE_MEDIA_LIVE", "1")
    saved_env.setenv("GIGMATE_MEDIA_API_KEY", "test-key")
    saved_env.setenv("GIGMATE_MEDIA_ALLOW_LIVE_ORIGIN", "1")
    saved_env.setenv("GIGMATE_MEDIA_CHAT_VENDOR", "openai")
    payload = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "coverage": "complete",
                            "summary": "A brief",
                            "suggestions": [
                                {
                                    "field": "schedule",
                                    "text": "next monday",
                                    "source_indices": [99],
                                }
                            ],
                            "unresolved_questions": [],
                        }
                    )
                }
            }
        ]
    }
    fake = _FakeClient(chat_payload=payload)
    saved_env.setattr(llm, "default_client_factory", lambda *, timeout: fake)
    with pytest.raises(ProcessingUncertain):
        MediaProcessorImpl().process(
            make_input(mimetype="application/pdf", content=_build_pdf("one page"))
        )


# Reconcile semantics


def test_reconcile_returns_none_when_closed(saved_seam_flag, saved_env):
    # Default: gates closed, reconcile returns None without vendor contact.
    assert MediaProcessorImpl().reconcile("req-1") is None


def test_reconcile_returns_none_when_open_no_lookup_implemented(saved_env, saved_seam_flag):
    mp._ENABLED = True
    saved_env.setenv("GIGMATE_MEDIA_LIVE", "1")
    assert MediaProcessorImpl().reconcile("req-1") is None


# Security boundary


def test_media_input_has_no_credentials(make_input_fixture=None):
    """The MediaInput dataclass must not carry API keys or provider URLs.

    The seam test in ``test_waha_media.py`` repeats this assertion for the
    legacy Processor stub; here we lock it down at the type layer.
    """

    inp = make_input()
    for attr in ("api_key", "provider_url", "api_endpoint", "authorization"):
        assert not hasattr(inp, attr), f"MediaInput must not expose {attr!r}"


def test_processor_does_not_mutate_input(saved_env, saved_seam_flag):
    mp._ENABLED = True
    saved_env.setenv("GIGMATE_MEDIA_LIVE", "1")
    saved_env.setenv("GIGMATE_MEDIA_API_KEY", "test-key")
    saved_env.setenv("GIGMATE_MEDIA_ALLOW_LIVE_ORIGIN", "1")
    saved_env.setenv("GIGMATE_MEDIA_CHAT_VENDOR", "openai")
    fake = _FakeClient(chat_payload=_chat_ok())
    saved_env.setattr(llm, "default_client_factory", lambda *, timeout: fake)
    request = make_input()
    snapshot_before = request.content
    MediaProcessorImpl().process(request)
    assert request.content == snapshot_before


def test_factory_resolves_to_media_processor_impl(monkeypatch):
    """The factory entry point must be reachable via the standard
    ``module:AttrName`` syntax used by ``gigmate.media_processing.processor``."""

    monkeypatch.setenv(
        "GIGMATE_MEDIA_PROCESSOR_FACTORY", "gigmate.media.processor:MediaProcessorImpl"
    )
    # Build directly via the factory entry point rather than re-importing to
    # keep the test resilient to monkeypatch ordering.
    proc = build_processor()
    assert isinstance(proc, MediaProcessorImpl)
    # The factory's callable check should also accept the build_processor entry.
    assert callable(getattr(proc, "process", None))
    assert callable(getattr(proc, "reconcile", None))


# ----------------------------------------------------------- helpers


class _FakeClient:
    """A minimal httpx.Client stand-in for hermetic tests.

    Records every ``post`` call and returns a configurable response. The
    implementation avoids depending on httpx internals so we do not have to
    update the fake each time httpx changes.
    """

    def __init__(
        self,
        *,
        chat_payload: dict[str, Any] | None = None,
        transcription_payload: dict[str, Any] | None = None,
        status_code: int = 200,
        body: bytes | None = None,
        raise_network: bool = False,
    ) -> None:
        self.chat_payload = chat_payload
        self.transcription_payload = transcription_payload
        self.status_code = status_code
        self.body = body
        self.raise_network = raise_network
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        self.calls.append((url, kwargs))
        if self.raise_network:
            raise httpx.ConnectError("simulated network error")
        if "/audio/transcriptions" in url:
            payload = self.transcription_payload or {}
            data = json.dumps(payload).encode("utf-8")
        elif self.body is not None:
            data = self.body
        else:
            payload = self.chat_payload or {}
            data = json.dumps(payload).encode("utf-8")
        return httpx.Response(self.status_code, content=data)

    def close(self) -> None:  # pragma: no cover - parity with httpx.Client
        return None
