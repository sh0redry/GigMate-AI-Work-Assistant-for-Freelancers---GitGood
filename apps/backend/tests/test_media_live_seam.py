"""Live media seam: the switch is operator-owned and every modality is named.

Covers the enabling matrix for real OCR / ASR / PDF / text shipping:

* the seam itself defaults to closed and is opened only by
  ``GIGMATE_MEDIA_ENABLED=1`` — flipping it is never sufficient on its own;
* opening the seam does not authorise a modality: ``GIGMATE_MEDIA_MODALITIES``
  still gates ocr / asr / pdf / text independently;
* an image-capable vendor must have been verified
  (``GIGMATE_MEDIA_VISION_VENDORS``) before image bytes may leave the process;
* audio additionally needs its own named vendor, so a deployment configured
  only for DeepSeek chat can never post that key to a default ASR endpoint.

Every case asserts a refusal *before* an HTTP client is built, so no test
needs network access.
"""

from __future__ import annotations

import hashlib

import pytest

from gigmate.media import llm
from gigmate.media.processor import MediaProcessorImpl, is_seam_enabled
from gigmate.media_processing import MediaInput, ProcessingUnavailable

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02"
    b"\x00\x00\x00\x90\x77\x53\xde\x00\x00\x00\x0cIDATx\x9cc```\x00\x00\x00\x04"
    b"\x00\x01\xf6\x178\x00\x00\x00\x00IEND\xaeB`\x82"
)
AUDIO = b"RIFF____WAVEfmt "
TEXT = "synthetic attachment body".encode()


def _input(mimetype: str, content: bytes) -> MediaInput:
    return MediaInput(
        request_id="req-seam",
        account_id="acct-seam",
        conversation_id="conv-seam",
        snapshot_id="snap-seam",
        attachment_id="att-seam",
        attachment_version=1,
        context_version=0,
        source_fingerprint="fp-seam",
        sha256=hashlib.sha256(content).hexdigest(),
        mimetype=mimetype,
        source_occurred_at="2026-10-10T00:00:00Z",
        content=content,
        caption="synthetic caption",
        origin="live",
    )


@pytest.fixture
def seam(monkeypatch):
    """Unlock every gate except the one under test."""

    for key in (
        "GIGMATE_MEDIA_ENABLED",
        "GIGMATE_MEDIA_LIVE",
        "GIGMATE_MEDIA_ALLOW_LIVE_ORIGIN",
        "GIGMATE_MEDIA_API_KEY",
        "GIGMATE_MEDIA_CHAT_VENDOR",
        "GIGMATE_MEDIA_CHAT_MODEL",
        "GIGMATE_MEDIA_AUDIO_VENDOR",
        "GIGMATE_MEDIA_AUDIO_MODEL",
        "GIGMATE_MEDIA_MODALITIES",
        "GIGMATE_MEDIA_VISION_VENDORS",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("GIGMATE_MEDIA_LIVE", "1")
    monkeypatch.setenv("GIGMATE_MEDIA_ALLOW_LIVE_ORIGIN", "1")
    monkeypatch.setenv("GIGMATE_MEDIA_API_KEY", "test-key")
    monkeypatch.setenv("GIGMATE_MEDIA_CHAT_VENDOR", "deepseek")
    monkeypatch.setenv("GIGMATE_MEDIA_CHAT_MODEL", "deepseek-chat")
    monkeypatch.setattr("gigmate.media.processor._ENABLED", False)
    return monkeypatch


def test_seam_is_closed_by_default(seam):
    assert is_seam_enabled() is False
    with pytest.raises(ProcessingUnavailable, match="_ENABLED"):
        MediaProcessorImpl().process(_input("image/png", PNG))


def test_seam_switch_is_read_from_the_environment(seam):
    seam.setenv("GIGMATE_MEDIA_ENABLED", "1")
    assert is_seam_enabled() is True
    # Past the seam the next gate is per-modality authorization, not the
    # vendor: nothing is authorized yet, so no request is built.
    with pytest.raises(ProcessingUnavailable, match="MEDIA_MODALITY_NOT_AUTHORIZED"):
        MediaProcessorImpl().process(_input("image/png", PNG))


def test_opening_the_seam_does_not_authorise_a_modality(seam):
    seam.setenv("GIGMATE_MEDIA_ENABLED", "1")
    for mimetype, content in (("image/png", PNG), ("audio/wav", AUDIO), ("text/plain", TEXT)):
        with pytest.raises(ProcessingUnavailable, match="MEDIA_MODALITY_NOT_AUTHORIZED"):
            MediaProcessorImpl().process(_input(mimetype, content))


def test_ocr_needs_a_verified_vision_vendor(seam):
    seam.setenv("GIGMATE_MEDIA_ENABLED", "1")
    seam.setenv("GIGMATE_MEDIA_MODALITIES", "ocr")
    with pytest.raises(ProcessingUnavailable, match="MEDIA_VISION_VENDOR_UNVERIFIED"):
        MediaProcessorImpl().process(_input("image/png", PNG))


class _FakeResponse:
    status_code = 200

    def __init__(self, body: dict):
        self._body = body

    def json(self) -> dict:
        return self._body


class _FakeClient:
    """Records the request instead of performing it; no network in tests."""

    def __init__(self):
        self.payloads = []

    def post(self, url: str, json=None, **_kwargs):
        self.payloads.append(json)
        return _FakeResponse(
            {
                "model": "deepseek-flash",
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"coverage": "partial", "segments": [{"index": 0,'
                                ' "text": "TUE 3PM"}], "suggestions": [{"field":'
                                ' "schedule", "text": "TUE 3PM", "source_indices":'
                                ' [0]}], "unresolved_questions": ["no date"]}'
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 885, "completion_tokens": 100},
            }
        )

    def close(self) -> None:
        return None


def test_ocr_runs_once_the_vision_vendor_is_verified(seam):
    seam.setenv("GIGMATE_MEDIA_ENABLED", "1")
    seam.setenv("GIGMATE_MEDIA_MODALITIES", "ocr")
    seam.setenv("GIGMATE_MEDIA_VISION_VENDORS", "deepseek")
    assert llm.is_vision_vendor_verified("deepseek") is True

    client = _FakeClient()
    seam.setattr(llm, "default_client_factory", lambda *, timeout: client)
    result = MediaProcessorImpl().process(_input("image/png", PNG))

    assert [segment.text for segment in result.segments] == ["TUE 3PM"]
    assert result.coverage == "partial"
    # The image really is the payload that leaves the process.
    sent = client.payloads[0]["messages"][1]["content"]
    assert any(part.get("type") == "image_url" for part in sent)


def test_audio_requires_its_own_named_vendor(seam):
    seam.setenv("GIGMATE_MEDIA_ENABLED", "1")
    seam.setenv("GIGMATE_MEDIA_MODALITIES", "asr")
    with pytest.raises(ProcessingUnavailable, match="MEDIA_AUDIO_VENDOR_REQUIRED"):
        MediaProcessorImpl().process(_input("audio/wav", AUDIO))


def test_audio_vendor_must_be_one_this_build_can_call(seam):
    seam.setenv("GIGMATE_MEDIA_ENABLED", "1")
    seam.setenv("GIGMATE_MEDIA_MODALITIES", "asr")
    # DeepSeek has no transcription endpoint in this build; naming it is an
    # explicit refusal, never a fallback onto OpenAI's default endpoint.
    seam.setenv("GIGMATE_MEDIA_AUDIO_VENDOR", "deepseek")
    with pytest.raises(ProcessingUnavailable, match="Unknown audio vendor"):
        MediaProcessorImpl().process(_input("audio/wav", AUDIO))


def test_vendor_bookkeeping_keys_are_dropped_not_trusted():
    """A real vendor adds keys the contract forbids; they are dropped.

    Captured from a live DeepSeek media response (synthetic image): the model
    emitted ``segments[].index`` because the prompt asks for 0-based
    ``source_indices``. Under ``extra=forbid`` that alone used to fail the
    whole proposal, so the extra keys are stripped instead of trusted — the
    position in the array is the index.
    """

    from gigmate.media.coercion import coerce_chat_response

    body = {
        "model": "deepseek-flash",
        "choices": [
            {
                "message": {
                    "content": (
                        '{"coverage": "partial", "segments": [{"index": 0, "kind":'
                        ' "image_region", "text": "TUE 3PM", "confidence": 0.91}],'
                        ' "suggestions": [{"field": "schedule", "text": "TUE 3PM",'
                        ' "source_indices": [0]}], "unresolved_questions":'
                        ' ["no date given"]}'
                    )
                }
            }
        ],
        "usage": {"prompt_tokens": 885, "completion_tokens": 100, "total_tokens": 985},
    }
    result = coerce_chat_response(
        body,
        prompt_version="1.1.0",
        vendor="deepseek",
        model_version="deepseek:deepseek-chat",
        caption=None,
    )
    assert [segment.text for segment in result.segments] == ["TUE 3PM"]
    # Server-side facts win over anything the vendor may claim.
    assert result.provider == "deepseek"
    assert result.prompt_version == "1.1.0"
    assert result.model_version == "deepseek:deepseek-chat"
    assert result.coverage == "partial"


def test_env_summary_never_echoes_the_key(seam):
    summary = llm.env_summary()
    assert "test-key" not in str(summary)
    assert summary["api_key"] != "test-key"
