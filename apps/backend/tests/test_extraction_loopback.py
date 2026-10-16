"""Real-socket regression for the extraction total deadline.

Every sibling module proves the vendor boundary with an injected test double.
This one deliberately does not: the review reproduced its finding over loopback
HTTP (roughly 0.36 s observed against a 0.18 s budget) and a double cannot show
that the *transfer itself* is torn down rather than merely abandoned. So this
module starts a loopback HTTP server that dribbles one chat-completions body
out, and drives the extraction client against it with a real ``httpx.Client``.

Scope is unchanged: loopback sockets only, no vendor, no credential, no
external network and no real model activation. The body the server serves is
synthetic, and the deadline is shortened by the test, never by configuration.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx

from gigmate.extraction import llm as llm_module
from gigmate.extraction.llm import LLMProvider
from gigmate.extraction.types import ExtractionRequest

ACCOUNT_ID = "00000000-0000-4000-8000-000000000001"
CONVERSATION_ID = "00000000-0000-4000-8000-000000000002"
MESSAGE_ID = "00000000-0000-4000-8000-000000000003"
CANDIDATE = "00000000-0000-4000-8000-000000000004"

_ENV_NAMES = (
    "GIGMATE_LLM_PROVIDER",
    "GIGMATE_LLM_MODEL",
    "GIGMATE_LLM_API_KEY",
    "GIGMATE_LLM_ENDPOINT",
    "GIGMATE_LLM_PROMPT_PATH",
    "GIGMATE_LLM_LIVE",
    "GIGMATE_LLM_ALLOW_LIVE_ORIGIN",
    "GIGMATE_LLM_COST_BUDGET_USD",
    "GIGMATE_LLM_COST_INPUT_USD_PER_1K",
    "GIGMATE_LLM_COST_OUTPUT_USD_PER_1K",
    "GIGMATE_LLM_MAX_INPUT_TOKENS",
    "GIGMATE_LLM_MAX_OUTPUT_TOKENS",
    "GIGMATE_WORKSPACE_TIMEZONE",
)


def _configure(monkeypatch, **extra) -> None:
    for name in _ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GIGMATE_LLM_PROVIDER", "openai")
    monkeypatch.setenv("GIGMATE_LLM_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("GIGMATE_LLM_API_KEY", "sk-fake-test")
    monkeypatch.setenv("GIGMATE_LLM_LIVE", "1")
    for key, value in extra.items():
        monkeypatch.setenv(key, value)


def _request() -> ExtractionRequest:
    return ExtractionRequest(
        account_id=ACCOUNT_ID,
        conversation_id=CONVERSATION_ID,
        message_id=MESSAGE_ID,
        message_revision=1,
        message_text="改下星期四下午三点，地址我晚些发",
        context_version=5,
        candidate_work_order_ids=(CANDIDATE,),
        base_work_order_version=3,
        base_work_order_snapshot=None,
        origin="synthetic",
        message_received_at="2026-10-07T00:00:00Z",
        workspace_timezone="Asia/Hong_Kong",
    )


def _gate_open_provider(client) -> LLMProvider:
    class _GateOpen(LLMProvider):
        _SKELETON_SEAM = False

    provider = _GateOpen()
    provider._client_factory = client
    return provider


def _trickling_server(*, chunk_delay: float, chunks: int):
    """A loopback HTTP server that dribbles one chat-completions body out."""
    body = json.dumps(
        {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {"assignment": "needs_review", "unresolved_questions": ["synthetic"]}
                        )
                    }
                }
            ]
        }
    ).encode("utf-8")

    class _Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802 - the http.server API name
            length = int(self.headers.get("Content-Length") or 0)
            if length:
                self.rfile.read(length)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            size = max(1, -(-len(body) // chunks))
            try:
                for start in range(0, len(body), size):
                    self.wfile.write(body[start : start + size])
                    self.wfile.flush()
                    time.sleep(chunk_delay)
            except (BrokenPipeError, ConnectionResetError):
                pass  # the client closed the response: the transfer really stopped

        def log_message(self, *args):
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def test_total_deadline_stops_a_real_response_that_keeps_arriving(monkeypatch):
    """The review's measurement, on a real socket instead of a test double.

    The server needs roughly ten seconds to finish the body. A deadline that is
    only consulted after the body has been read would wait for all of it;
    aborting the read has to return at the declared budget and leave the call
    recorded as ``llm:deadline-exceeded`` with its request id.
    """
    # 3 s is the smallest budget that still leaves one attempt a usable read
    # window after pool/connect/write (see ``_MIN_REQUEST_TIMEOUT_S``), so the
    # request really is issued before it is stopped.
    monkeypatch.setattr(llm_module, "_TOTAL_DEADLINE_S", 3.0)
    server, thread = _trickling_server(chunk_delay=0.05, chunks=200)
    try:
        host, port = server.server_address[0], server.server_address[1]
        _configure(monkeypatch, GIGMATE_LLM_ENDPOINT=f"http://{host}:{port}")
        provider = _gate_open_provider(httpx.Client)
        began = time.monotonic()
        outcome = provider.propose(_request())
        elapsed = time.monotonic() - began
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert outcome.notes == ("llm:deadline-exceeded",)
    assert outcome.refused_reason == "llm:deadline-exceeded"
    assert outcome.request_id
    # The whole body would have taken about ten seconds; the lower bound proves
    # the request was really issued rather than skipped for lack of a window.
    assert 2.0 < elapsed < 6.0
