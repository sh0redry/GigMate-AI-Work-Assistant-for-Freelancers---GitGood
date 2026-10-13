import json
import os
import sys
import threading
import time

import pytest
from test_media_processor import _build_pdf
from test_media_processor import saved_env as saved_env
from test_media_processor import saved_seam_flag as saved_seam_flag

from gigmate import worker
from gigmate.media import pdf_isolation as isolation
from gigmate.media.pdfparse import PdfParseError, extract

NATIVE_SUPPORTED = sys.platform.startswith("linux") or os.name == "nt"
supported = pytest.mark.skipif(
    not NATIVE_SUPPORTED, reason="Native platform fails closed; use Linux Docker"
)


def fixture_child(tmp_path, monkeypatch, code):
    """Trusted fixture inherits the production resource limiter, never a public hook."""
    path = tmp_path / "child.py"
    source = f"""import json, os, sys, runpy, time
guard = runpy.run_path({str(isolation.child_path())!r})
guard['set_limits'](int(sys.argv[1]), float(sys.argv[2]))
guard['bind_parent'](int(sys.argv[4]))
print(json.dumps({{'ready':os.getpid()}}), flush=True)
assert sys.stdin.buffer.read(1) == b'1'
sys.stdin.buffer.read()
{code}
"""
    path.write_text(source, encoding="utf-8")
    monkeypatch.setattr(isolation, "child_path", lambda: path)
    return path


@supported
def test_real_pdf_parse_is_in_a_child_and_preserves_pages():
    result = extract(_build_pdf("Synthetic first", "Second page"))
    assert [(p.page, p.text) for p in result.pages] == [(1, "Synthetic first"), (2, "Second page")]


@supported
def test_timeout_terminates_and_reaps_owned_child(tmp_path, monkeypatch):
    fixture_child(tmp_path, monkeypatch, "time.sleep(30)")
    created = []
    original = isolation.subprocess.Popen

    def capture(*args, **kwargs):
        process = original(*args, **kwargs)
        created.append(process)
        return process

    monkeypatch.setattr(isolation.subprocess, "Popen", capture)
    began = time.monotonic()
    with pytest.raises(PdfParseError, match="MEDIA_PDF_TIMEOUT"):
        isolation.run_child(b"synthetic", isolation.Limits(0.5))
    assert time.monotonic() - began < 8
    assert created and created[0].poll() is not None
    assert created[0].stdin.closed and created[0].stdout.closed


@supported
def test_os_memory_limit_is_real_not_a_mock(tmp_path, monkeypatch):
    fixture_child(
        tmp_path,
        monkeypatch,
        """try:
    data = bytearray(512 * 1024 * 1024)
    data[:] = b'x' * len(data)
    print(json.dumps({'pages':[{'page':1,'text':'UNRESTRICTED'}], 'total_pages':1,'empty_pages':0}))
except MemoryError:
    print(json.dumps({'error':'MEDIA_PDF_MEMORY_LIMIT'}))""",
    )
    with pytest.raises(PdfParseError, match="MEDIA_PDF_MEMORY_LIMIT|MEDIA_PDF_CHILD_TERMINATED"):
        isolation.run_child(b"synthetic", isolation.Limits(5, 128 * 1024 * 1024))


@supported
@pytest.mark.parametrize(
    "code,error",
    [
        ("os._exit(17)", "CHILD_TERMINATED"),
        ("print('not-json')", "PROTOCOL_INVALID"),
        ("sys.stdout.write('x'*2000000);sys.stdout.flush()", "OUTPUT_LIMIT"),
    ],
)
def test_child_failures_are_bounded_and_not_success(tmp_path, monkeypatch, code, error):
    fixture_child(tmp_path, monkeypatch, code)
    with pytest.raises(PdfParseError, match=error):
        isolation.run_child(b"synthetic", isolation.Limits(5))


@supported
def test_credentials_and_worker_environment_are_not_inherited(tmp_path, monkeypatch):
    for key in (
        "GIGMATE_MEDIA_API_KEY",
        "WAHA_API_KEY",
        "DATABASE_URL",
        "PYTHONPATH",
        "GIGMATE_LLM_API_KEY",
    ):
        monkeypatch.setenv(key, "synthetic-sensitive-value")
    fixture_child(
        tmp_path,
        monkeypatch,
        """assert not any(k in os.environ for k in ('GIGMATE_MEDIA_API_KEY','WAHA_API_KEY','DATABASE_URL','PYTHONPATH','GIGMATE_LLM_API_KEY'))
print(json.dumps({'pages':[{'page':1,'text':str(os.getpid())}], 'total_pages':1,'empty_pages':0}))""",
    )
    result = isolation.run_child(b"synthetic", isolation.Limits(5))
    assert int(result.pages[0].text) != os.getpid()


def test_limit_setup_failure_does_not_release_pdf_input(tmp_path, monkeypatch):
    marker = tmp_path / "parsed.txt"
    fixture_child(tmp_path, monkeypatch, f"open({str(marker)!r},'w').write('unexpected')")

    def refuse(*args):
        raise OSError

    monkeypatch.setattr(isolation, "attach", refuse)
    with pytest.raises(PdfParseError, match="LIMIT_UNAVAILABLE"):
        isolation.run_child(b"synthetic", isolation.Limits(5))
    assert not marker.exists()


@pytest.mark.parametrize("value", ["0", "nan", "61", "invalid"])
def test_bad_limit_configuration_fails_clearly(monkeypatch, value):
    monkeypatch.setenv("GIGMATE_PDF_TIMEOUT_SECONDS", value)
    with pytest.raises(PdfParseError, match="CONFIG_INVALID"):
        isolation.configured_limits()


def test_busy_does_not_launch_a_second_parser(monkeypatch):
    assert isolation._slot.acquire(blocking=False)
    try:
        with pytest.raises(PdfParseError, match="BUSY"):
            extract(b"synthetic")
    finally:
        isolation._slot.release()


def test_parent_validates_page_and_output_limits():
    for data in [
        {"pages": [{"page": 2, "text": "wrong"}], "total_pages": 1, "empty_pages": 0},
        {"pages": [{"page": 1, "text": "x" * 4001}], "total_pages": 1, "empty_pages": 0},
        {"pages": [], "total_pages": 1, "empty_pages": 0},
    ]:
        with pytest.raises(PdfParseError, match="PROTOCOL_INVALID"):
            isolation.validate_result(json.dumps(data))


@supported
def test_wrong_child_identity_never_receives_pdf(tmp_path, monkeypatch):
    marker = tmp_path / "received.txt"
    path = fixture_child(tmp_path, monkeypatch, f"open({str(marker)!r},'w').write('unexpected')")
    source = path.read_text(encoding="utf-8").replace(
        "'ready':os.getpid()", "'ready':os.getpid()+1"
    )
    path.write_text(source, encoding="utf-8")
    with pytest.raises(PdfParseError, match="LIMIT_UNAVAILABLE"):
        isolation.run_child(b"synthetic", isolation.Limits(5))
    assert not marker.exists()


@supported
def test_utf8_ipc_preserves_text(tmp_path, monkeypatch):
    fixture_child(
        tmp_path,
        monkeypatch,
        "print(json.dumps({'pages':[{'page':1,'text':'合成订单文字'}],'total_pages':1,'empty_pages':0},ensure_ascii=False))",
    )
    assert isolation.run_child(b"synthetic", isolation.Limits(5)).pages[0].text == "合成订单文字"


@supported
def test_parser_timeout_never_constructs_vendor_client(tmp_path, saved_env, saved_seam_flag):
    from test_media_processor import MediaProcessorImpl, llm, make_input, mp

    from gigmate.media_processing import ProcessingUnavailable

    mp._ENABLED = True
    for key, value in {
        "GIGMATE_MEDIA_LIVE": "1",
        "GIGMATE_MEDIA_API_KEY": "synthetic",
        "GIGMATE_MEDIA_CHAT_VENDOR": "openai",
        "GIGMATE_PDF_TIMEOUT_SECONDS": "1",
    }.items():
        saved_env.setenv(key, value)
    fixture_child(tmp_path, saved_env, "time.sleep(30)")
    saved_env.setattr(
        llm, "default_client_factory", lambda **kwargs: pytest.fail("vendor client created")
    )
    with pytest.raises(ProcessingUnavailable, match="MEDIA_PDF_TIMEOUT"):
        MediaProcessorImpl().process(
            make_input(
                mimetype="application/pdf", content=_build_pdf("synthetic"), origin="synthetic"
            )
        )


@supported
def test_after_pdf_parse_authority_is_checked_before_client(saved_env, saved_seam_flag):
    from dataclasses import replace

    from test_media_processor import MediaProcessorImpl, llm, make_input, mp

    from gigmate.media_processing import ProcessingUnavailable

    mp._ENABLED = True
    for key, value in {
        "GIGMATE_MEDIA_LIVE": "1",
        "GIGMATE_MEDIA_API_KEY": "synthetic",
        "GIGMATE_MEDIA_CHAT_VENDOR": "openai",
    }.items():
        saved_env.setenv(key, value)
    seen = []

    def refuse():
        seen.append(True)
        raise ProcessingUnavailable("MEDIA_PROCESSING_PERMISSION_CHANGED")

    saved_env.setattr(
        llm, "default_client_factory", lambda **kwargs: pytest.fail("vendor client created")
    )
    request = replace(
        make_input(mimetype="application/pdf", content=_build_pdf("synthetic"), origin="synthetic"),
        before_submit=refuse,
    )
    with pytest.raises(ProcessingUnavailable, match="PERMISSION_CHANGED"):
        MediaProcessorImpl().process(request)
    assert seen == [True]


def test_heartbeat_continues_while_worker_is_busy(monkeypatch):
    stop = threading.Event()
    calls = []
    monkeypatch.setattr(worker, "heartbeat", lambda factory: calls.append(time.monotonic()))
    thread = threading.Thread(target=worker.heartbeat_loop, args=(stop, None, 0.02))
    thread.start()
    try:
        time.sleep(0.1)
        assert len(calls) >= 2
    finally:
        stop.set()
        thread.join(timeout=1)
    assert not thread.is_alive()


@pytest.mark.skipif(NATIVE_SUPPORTED, reason="Unsupported native-platform contract")
def test_unsupported_native_platform_refuses_before_pdf_parse():
    with pytest.raises(PdfParseError, match="LIMIT_UNAVAILABLE"):
        extract(_build_pdf("synthetic"))
