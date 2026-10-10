import importlib.util
import json
from argparse import Namespace
from pathlib import Path

import pytest
from test_media_processor import make_input

from gigmate.media import llm
from gigmate.media.coercion import coerce_chat_response, coerce_transcription_response
from gigmate.media.processor import MediaProcessorImpl
from gigmate.media_processing import ProcessingUnavailable, ProcessingUncertain


@pytest.mark.parametrize("error", [ProcessingUnavailable, ProcessingUncertain])
def test_smoke_refusal_and_unknown_are_nonzero(monkeypatch, tmp_path, error):
    path = Path(__file__).resolve().parents[3] / "scripts" / "smoke_media.py"
    spec = importlib.util.spec_from_file_location("smoke_media_review", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sample = tmp_path / "sample.txt"
    sample.write_text("synthetic", encoding="utf-8")
    monkeypatch.setattr(
        module,
        "parse_args",
        lambda: Namespace(
            file=sample, mime="text/plain", origin="synthetic", caption=None, request_id="synthetic"
        ),
    )

    def refuse(*args):
        raise error("synthetic refusal")

    monkeypatch.setattr(MediaProcessorImpl, "process", refuse)
    assert module.main() == 1


@pytest.mark.parametrize(
    "mime,content,vendor,code",
    [
        ("application/pdf", b"%PDF-synthetic", "openai", "PDF_PARSER_PENDING"),
        ("image/png", b"synthetic", "deepseek", "VISION_VENDOR_UNVERIFIED"),
        ("text/plain", b"\xff", "openai", "TEXT_ENCODING_INVALID"),
        ("text/plain", b"a" * 90001, "openai", "TEXT_CHUNKING_PENDING"),
        ("text/plain", b"synthetic", "custom", "CUSTOM_ENDPOINT_REQUIRED"),
    ],
    ids=["pdf", "vision", "encoding", "long-text", "custom"],
)
def test_unimplemented_routes_refuse_before_client(monkeypatch, mime, content, vendor, code):
    monkeypatch.setattr("gigmate.media.processor._ENABLED", True)
    monkeypatch.setenv("GIGMATE_MEDIA_LIVE", "1")
    monkeypatch.setenv("GIGMATE_MEDIA_API_KEY", "synthetic-key")
    monkeypatch.setenv("GIGMATE_MEDIA_CHAT_VENDOR", vendor)
    monkeypatch.delenv("GIGMATE_MEDIA_ENDPOINT", raising=False)
    monkeypatch.setattr(
        llm, "default_client_factory", lambda **kwargs: pytest.fail("client constructed")
    )
    with pytest.raises(ProcessingUnavailable, match=code):
        MediaProcessorImpl().process(make_input(mimetype=mime, content=content, origin="synthetic"))


def test_non_utf8_prompt_is_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr("gigmate.media.processor._ENABLED", True)
    monkeypatch.setenv("GIGMATE_MEDIA_LIVE", "1")
    monkeypatch.setenv("GIGMATE_MEDIA_API_KEY", "synthetic-key")
    path = tmp_path / "prompt.txt"
    path.write_bytes(b"\xff")
    monkeypatch.setenv("GIGMATE_MEDIA_PROMPT_PATH", str(path))
    with pytest.raises(ProcessingUnavailable):
        MediaProcessorImpl().process(make_input(origin="synthetic"))


def test_long_transcript_keeps_every_character_with_unknown_coverage():
    text = "s" * 9000
    result = coerce_transcription_response(
        {"text": text}, prompt_version="1", vendor="test", model_version="test"
    )
    assert "".join(segment.text for segment in result.segments) == text
    assert result.coverage == "unknown"


@pytest.mark.parametrize(
    "segments,suggestions",
    [
        ([{"text": "a" * 4001}], []),
        ([{"text": ""}], [{"field": "summary", "value": "test", "source_indices": [1]}]),
        ([{"text": "ok"}], [{"field": "summary", "value": "test", "source_indices": [2]}]),
    ],
)
def test_invalid_result_is_not_silently_trimmed_or_reindexed(segments, suggestions):
    data = {"coverage": "complete", "segments": segments, "suggestions": suggestions}
    with pytest.raises(ProcessingUncertain):
        coerce_chat_response(
            {"choices": [{"message": {"content": json.dumps(data)}}]},
            prompt_version="1",
            vendor="test",
            model_version="test",
        )


@pytest.mark.parametrize("failed", [False, True])
def test_client_is_closed_and_raw_error_not_logged(monkeypatch, caplog, failed):
    monkeypatch.setattr("gigmate.media.processor._ENABLED", True)
    for name, value in {
        "GIGMATE_MEDIA_LIVE": "1",
        "GIGMATE_MEDIA_API_KEY": "synthetic-key",
        "GIGMATE_MEDIA_CHAT_VENDOR": "openai",
    }.items():
        monkeypatch.setenv(name, value)

    class Client:
        closed = False

        def close(self):
            self.closed = True

    client = Client()
    monkeypatch.setattr(llm, "default_client_factory", lambda **kwargs: client)

    def call(**kwargs):
        if failed:
            raise RuntimeError("synthetic-secret-provider-response")
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {"segments": [{"text": "synthetic"}], "coverage": "unknown"}
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr(llm, "chat_completions", call)
    if failed:
        with pytest.raises(ProcessingUncertain, match="MEDIA_VENDOR_RESULT_UNKNOWN"):
            MediaProcessorImpl().process(make_input(origin="synthetic"))
    else:
        MediaProcessorImpl().process(make_input(origin="synthetic"))
    assert client.closed
    assert "synthetic-secret-provider-response" not in caplog.text
