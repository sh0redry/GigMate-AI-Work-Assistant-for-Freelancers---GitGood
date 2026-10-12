import pypdf
import pytest
from test_media_processor import (
    MediaProcessorImpl,
    _build_pdf,
    _FakeClient,
    _pdf_ok,
    llm,
    make_input,
    mp,
)
from test_media_processor import saved_env as saved_env
from test_media_processor import saved_seam_flag as saved_seam_flag

from gigmate.media import pdfparse


def test_missing_page_text_overrides_model_complete_claim(saved_env, saved_seam_flag):
    mp._ENABLED = True
    for key, value in {
        "GIGMATE_MEDIA_LIVE": "1",
        "GIGMATE_MEDIA_API_KEY": "synthetic",
        "GIGMATE_MEDIA_ALLOW_LIVE_ORIGIN": "1",
        "GIGMATE_MEDIA_CHAT_VENDOR": "openai",
    }.items():
        saved_env.setenv(key, value)
    saved_env.setattr(
        llm, "default_client_factory", lambda **kwargs: _FakeClient(chat_payload=_pdf_ok())
    )
    result = MediaProcessorImpl().process(
        make_input(mimetype="application/pdf", content=_build_pdf("synthetic text", ""))
    )
    assert result.unresolved_questions
    assert result.coverage == "partial"


def test_text_limit_stops_before_reading_next_page(monkeypatch):
    visited = []

    class Page:
        def __init__(self, index):
            self.index = index

        def extract_text(self):
            visited.append(self.index)
            return "x" * 11

    class Reader:
        def __init__(self, *args):
            self.pages = [Page(1), Page(2)]

    monkeypatch.setattr(pypdf, "PdfReader", Reader)
    monkeypatch.setattr(pdfparse, "MAX_TOTAL_TEXT", 10)
    with pytest.raises(pdfparse.PdfParseError, match="TEXT_LIMIT"):
        pdfparse.extract(b"synthetic")
    assert visited == [1]
