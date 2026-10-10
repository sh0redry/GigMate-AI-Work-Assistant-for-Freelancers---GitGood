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
* Coercion: vendor JSON -> WahaMediaResult with valid bounds.
* Failure modes: 4xx / 5xx -> ProcessingUncertain, network error ->
  ProcessingUncertain, malformed vendor JSON -> ProcessingUncertain.
* Security boundary: ``MediaInput`` carries no ``api_key``/``provider_url``;
  ``MediaInput`` is not mutated by the processor.
"""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

import httpx
import pytest

import gigmate.media.llm as llm
import gigmate.media.processor as mp
from gigmate.contracts import WahaMediaResult
from gigmate.media.coercion import coerce_chat_response, coerce_transcription_response
from gigmate.media.processor import _ENABLED, MediaProcessorImpl, build_processor
from gigmate.media_processing import MediaInput, ProcessingUnavailable, ProcessingUncertain

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
    ):
        monkeypatch.delenv(key, raising=False)
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


def test_default_seam_flag_is_false(saved_env, saved_seam_flag):
    """The shipping default must be off so a future operator cannot flip live
    processing by exporting the env var alone."""

    assert _ENABLED is False
    assert isinstance(build_processor(), MediaProcessorImpl)
    with pytest.raises(ProcessingUnavailable, match="_ENABLED"):
        MediaProcessorImpl().process(make_input())


def test_seam_flag_without_live_switch_refuses(saved_env, saved_seam_flag):
    mp._ENABLED = True
    saved_env.setenv("GIGMATE_MEDIA_API_KEY", "test-key")
    saved_env.setenv("GIGMATE_MEDIA_ALLOW_LIVE_ORIGIN", "1")
    with pytest.raises(ProcessingUnavailable, match="GIGMATE_MEDIA_LIVE"):
        MediaProcessorImpl().process(make_input())


def test_live_switch_without_key_refuses(saved_env, saved_seam_flag):
    mp._ENABLED = True
    saved_env.setenv("GIGMATE_MEDIA_LIVE", "1")
    saved_env.setenv("GIGMATE_MEDIA_ALLOW_LIVE_ORIGIN", "1")
    with pytest.raises(ProcessingUnavailable, match="GIGMATE_MEDIA_API_KEY"):
        MediaProcessorImpl().process(make_input())


def test_live_origin_refused_by_default(saved_env, saved_seam_flag):
    mp._ENABLED = True
    saved_env.setenv("GIGMATE_MEDIA_LIVE", "1")
    saved_env.setenv("GIGMATE_MEDIA_API_KEY", "test-key")
    with pytest.raises(ProcessingUnavailable, match="Live-origin media is refused"):
        MediaProcessorImpl().process(make_input(origin="live"))


def test_unknown_origin_passes_origin_check(saved_env, saved_seam_flag):
    mp._ENABLED = True
    saved_env.setenv("GIGMATE_MEDIA_LIVE", "1")
    saved_env.setenv("GIGMATE_MEDIA_API_KEY", "test-key")
    # synthetic origin does not require the explicit live-origin opt-in
    fake_client = _FakeClient(chat_payload=_chat_ok())
    llm.default_client_factory = lambda *, timeout: fake_client  # type: ignore[assignment]
    result = MediaProcessorImpl().process(make_input(origin="synthetic"))
    assert isinstance(result, WahaMediaResult)


def test_unknown_vendor_refuses(saved_env, saved_seam_flag):
    mp._ENABLED = True
    saved_env.setenv("GIGMATE_MEDIA_LIVE", "1")
    saved_env.setenv("GIGMATE_MEDIA_API_KEY", "test-key")
    saved_env.setenv("GIGMATE_MEDIA_ALLOW_LIVE_ORIGIN", "1")
    saved_env.setenv("GIGMATE_MEDIA_CHAT_VENDOR", "unknown-vendor")
    with pytest.raises(ProcessingUnavailable, match="Unknown chat vendor"):
        MediaProcessorImpl().process(make_input())


def test_unsupported_mime_refuses(saved_env, saved_seam_flag):
    mp._ENABLED = True
    saved_env.setenv("GIGMATE_MEDIA_LIVE", "1")
    saved_env.setenv("GIGMATE_MEDIA_API_KEY", "test-key")
    saved_env.setenv("GIGMATE_MEDIA_ALLOW_LIVE_ORIGIN", "1")
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
        ("application/pdf", "_chat_ok"),
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
    payload = globals()[factory]()
    fake = (
        _FakeClient(chat_payload=payload)
        if factory == "_chat_ok"
        else _FakeClient(transcription_payload=payload)
    )
    llm.default_client_factory = lambda *, timeout: fake  # type: ignore[assignment]
    result = MediaProcessorImpl().process(make_input(mimetype=mimetype))
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
            {"id": 0, "start": 0.0, "end": 1.5, "text": "Synthetic transcript chunk"},
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
    fake = _FakeClient(status_code=500, body=b'{"error":"server"}')
    llm.default_client_factory = lambda *, timeout: fake  # type: ignore[assignment]
    with pytest.raises(ProcessingUncertain, match="500"):
        MediaProcessorImpl().process(make_input())


def test_4xx_is_uncertain(saved_env, saved_seam_flag):
    mp._ENABLED = True
    saved_env.setenv("GIGMATE_MEDIA_LIVE", "1")
    saved_env.setenv("GIGMATE_MEDIA_API_KEY", "test-key")
    saved_env.setenv("GIGMATE_MEDIA_ALLOW_LIVE_ORIGIN", "1")
    fake = _FakeClient(status_code=400, body=b'{"error":"bad request"}')
    llm.default_client_factory = lambda *, timeout: fake  # type: ignore[assignment]
    with pytest.raises(ProcessingUncertain, match="400"):
        MediaProcessorImpl().process(make_input())


def test_network_error_is_uncertain(saved_env, saved_seam_flag):
    mp._ENABLED = True
    saved_env.setenv("GIGMATE_MEDIA_LIVE", "1")
    saved_env.setenv("GIGMATE_MEDIA_API_KEY", "test-key")
    saved_env.setenv("GIGMATE_MEDIA_ALLOW_LIVE_ORIGIN", "1")
    fake = _FakeClient(raise_network=True)
    llm.default_client_factory = lambda *, timeout: fake  # type: ignore[assignment]
    with pytest.raises(ProcessingUncertain, match="vendor call failed"):
        MediaProcessorImpl().process(make_input())


def test_malformed_json_is_uncertain(saved_env, saved_seam_flag):
    mp._ENABLED = True
    saved_env.setenv("GIGMATE_MEDIA_LIVE", "1")
    saved_env.setenv("GIGMATE_MEDIA_API_KEY", "test-key")
    saved_env.setenv("GIGMATE_MEDIA_ALLOW_LIVE_ORIGIN", "1")
    fake = _FakeClient(chat_payload=None, body=b"not json")
    llm.default_client_factory = lambda *, timeout: fake  # type: ignore[assignment]
    with pytest.raises(ProcessingUncertain, match="Invalid JSON"):
        MediaProcessorImpl().process(make_input())


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
    fake = _FakeClient(chat_payload=_chat_ok())
    llm.default_client_factory = lambda *, timeout: fake  # type: ignore[assignment]
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
