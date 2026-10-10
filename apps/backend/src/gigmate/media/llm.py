"""Vendor adapters for the media processor.

Two endpoints are needed:

* OpenAI-compatible ``/v1/chat/completions`` for OCR (image), PDF and plain
  text. Default vendor: DeepSeek. Any OpenAI-compatible vendor (``openai``,
  ``custom``) is supported through the same call shape so the next batch only
  has to extend :func:`_resolve_endpoint`.
* OpenAI-compatible ``/v1/audio/transcriptions`` for ASR (audio). Default
  vendor: OpenAI. DeepSeek does not expose a transcription endpoint, so the
  processor refuses ASR with an explicit reason when only ``GIGMATE_LLM_*``
  variables are set; see :meth:`MediaProcessorImpl._audio_vendor`.

Both adapters accept an ``httpx.Client`` so tests can inject a fake client and
verify the request shape without hitting the network. The real client is built
from the operator's environment in :func:`default_client_factory`; it never
embeds the API key in the URL or logs it.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Mapping, Protocol

import httpx

from .routing import route

log = logging.getLogger(__name__)

_LIVE_GATE = "GIGMATE_MEDIA_LIVE"
_LIVE_ORIGIN_GATE = "GIGMATE_MEDIA_ALLOW_LIVE_ORIGIN"
_CHAT_VENDOR_ENV = "GIGMATE_MEDIA_CHAT_VENDOR"
_CHAT_MODEL_ENV = "GIGMATE_MEDIA_CHAT_MODEL"
_AUDIO_VENDOR_ENV = "GIGMATE_MEDIA_AUDIO_VENDOR"
_AUDIO_MODEL_ENV = "GIGMATE_MEDIA_AUDIO_MODEL"
_API_KEY_ENV = "GIGMATE_MEDIA_API_KEY"
_ENDPOINT_ENV = "GIGMATE_MEDIA_ENDPOINT"

_PROMPT_PATH_ENV = "GIGMATE_MEDIA_PROMPT_PATH"
_DEFAULT_PROMPT_FILENAME = "role_b_media_v1.txt"
_PROMPT_VERSION_PREFIX = "prompt_version:"
_PROMPT_VERSION_PENDING = "0.0.0-skeleton"

_KNOWN_CHAT_VENDORS = frozenset({"deepseek", "openai", "custom"})
_KNOWN_AUDIO_VENDORS = frozenset({"openai", "custom"})

_DEEPSEEK_DEFAULT_ENDPOINT = "https://api.deepseek.com"
_OPENAI_DEFAULT_ENDPOINT = "https://api.openai.com"


class MediaIntegrationPending(RuntimeError):
    """Raised when the seam is not yet wired or the operator switch is off.

    The processor translates this into :class:`ProcessingUnavailable` (no
    request was submitted) so the worker reports the clear
    ``MEDIA_PROCESSOR_NOT_CONFIGURED`` error code.
    """


class MediaVendorRejected(RuntimeError):
    """Raised when the vendor returned a 4xx / schema-failure response.

    The processor translates this into :class:`ProcessingUncertain` because
    the call may have incurred cost on the vendor side; the worker must use
    ``reconcile()`` rather than automatic resubmission.
    """


class ClientFactory(Protocol):
    def __call__(self, *, timeout: float) -> httpx.Client: ...


def default_client_factory(*, timeout: float) -> httpx.Client:
    """Build an httpx client with the API key as Bearer auth.

    The key is read on every call and never stored on the instance. The
    factory is intentionally not cached so a long-running worker can pick up
    a rotated key on the next call.
    """

    api_key = os.environ.get(_API_KEY_ENV, "")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    return httpx.Client(timeout=timeout, headers=headers)


def _resolve_chat_vendor() -> str:
    vendor = os.environ.get(_CHAT_VENDOR_ENV, "deepseek").strip().lower()
    if vendor not in _KNOWN_CHAT_VENDORS:
        raise MediaIntegrationPending(
            f"Unknown chat vendor {vendor!r}; supported: {sorted(_KNOWN_CHAT_VENDORS)}"
        )
    return vendor


def _resolve_audio_vendor() -> str:
    vendor = os.environ.get(_AUDIO_VENDOR_ENV, "openai").strip().lower()
    if vendor not in _KNOWN_AUDIO_VENDORS:
        raise MediaIntegrationPending(
            f"Unknown audio vendor {vendor!r}; supported: {sorted(_KNOWN_AUDIO_VENDORS)}"
        )
    return vendor


def _resolve_chat_endpoint(vendor: str) -> str:
    override = os.environ.get(_ENDPOINT_ENV, "").strip()
    if override:
        return override.rstrip("/")
    if vendor == "openai":
        return _OPENAI_DEFAULT_ENDPOINT
    if vendor == "custom":
        raise MediaIntegrationPending("MEDIA_CUSTOM_ENDPOINT_REQUIRED")
    return _DEEPSEEK_DEFAULT_ENDPOINT


def _chat_model_version(vendor: str, model: str | None) -> str:
    return f"{vendor}:{model or 'pending'}"


def _audio_model_version(vendor: str, model: str | None) -> str:
    return f"{vendor}:{model or 'pending'}"


def resolve_prompt_path(default_dir: Path | None = None) -> Path:
    override = os.environ.get(_PROMPT_PATH_ENV, "").strip()
    if override:
        return Path(override)
    base = default_dir or Path(__file__).resolve().parent / "prompts"
    return base / _DEFAULT_PROMPT_FILENAME


def read_prompt_version(path: Path) -> str:
    """Read the ``prompt_version:`` header from a prompt file.

    Returns :data:`_PROMPT_VERSION_PENDING` on any read/parse failure so the
    audit trail always carries a version string. The caller is expected to
    refuse the request when the placeholder is returned.
    """

    try:
        with path.open("r", encoding="utf-8") as handle:
            for raw in handle:
                stripped = raw.strip()
                if stripped.startswith(_PROMPT_VERSION_PREFIX):
                    value = stripped[len(_PROMPT_VERSION_PREFIX) :].strip()
                    return value or _PROMPT_VERSION_PENDING
    except (OSError, UnicodeError):
        return _PROMPT_VERSION_PENDING
    return _PROMPT_VERSION_PENDING


def chat_completions(
    *,
    client: httpx.Client,
    endpoint: str,
    model: str,
    prompt: str,
    mimetype: str,
    content: bytes,
    caption: str | None,
    extra_user: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """POST a chat-completions request and return the parsed JSON body.

    Raises :class:`MediaVendorRejected` on 4xx/5xx so the caller can translate
    to ``ProcessingUncertain``. Network / JSON errors propagate so the caller
    can decide between ``ProcessingUnavailable`` and ``ProcessingUncertain``.
    """

    user_content: list[dict[str, Any]] = []
    if caption:
        user_content.append({"type": "text", "text": f"Caption: {caption}"})
    if mimetype.startswith("image/"):
        import base64

        encoded = base64.b64encode(content).decode("ascii")
        user_content.append(
            {"type": "image_url", "image_url": {"url": f"data:{mimetype};base64,{encoded}"}}
        )
    else:
        # Plain text only: ship the raw bytes inline as a text snippet. Real vendors
        # accept this for short attachments; long attachments should be
        # uploaded by an upstream batch and referenced by URL.
        try:
            decoded = content.decode("utf-8")
        except Exception as exc:  # pragma: no cover - defensive
            raise MediaVendorRejected(f"Cannot decode {mimetype} bytes: {exc}") from exc
        user_content.append({"type": "text", "text": decoded})
    if extra_user:
        user_content.append({"type": "text", "text": json.dumps(extra_user, ensure_ascii=False)})

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    response = client.post(f"{endpoint}/v1/chat/completions", json=payload)
    if response.status_code >= 400:
        raise MediaVendorRejected(f"MEDIA_CHAT_HTTP_{response.status_code}")
    try:
        body = response.json()
    except json.JSONDecodeError as exc:
        raise MediaVendorRejected(f"Invalid JSON from chat completions: {exc}") from exc
    return body


def audio_transcriptions(
    *,
    client: httpx.Client,
    endpoint: str,
    model: str,
    mimetype: str,
    content: bytes,
    caption: str | None,
) -> dict[str, Any]:
    """POST an audio-transcription request and return the parsed JSON body.

    The response shape is vendor-specific; we normalise to ``{"text": ...,
    "segments": [...]}`` and let the processor coerce into a
    :class:`WahaMediaResult`.
    """

    suffix = mimetype.split("/", 1)[-1].replace("x-m4a", "m4a") or "bin"
    files = {"file": (f"audio.{suffix}", content, mimetype)}
    data: dict[str, str] = {"model": model, "response_format": "json"}
    if caption:
        data["prompt"] = caption
    response = client.post(f"{endpoint}/v1/audio/transcriptions", data=data, files=files)
    if response.status_code >= 400:
        raise MediaVendorRejected(f"MEDIA_AUDIO_HTTP_{response.status_code}")
    try:
        body = response.json()
    except json.JSONDecodeError as exc:
        raise MediaVendorRejected(f"Invalid JSON from transcriptions: {exc}") from exc
    return body


def dispatch_key(mimetype: str) -> str:
    """Re-export of :func:`gigmate.media.routing.route` for callers that
    only need to know which adapter handles a given MIME."""

    return route(mimetype)


def is_live_unlocked() -> bool:
    """Return True only when the operator has explicitly enabled live calls.

    The check is intentionally cheap (env-only) so the processor can refuse
    before doing any expensive work.
    """

    return os.environ.get(_LIVE_GATE, "").strip() == "1"


def is_live_origin_allowed() -> bool:
    """Return True only when the operator has explicitly allowed live-origin
    input to reach the model. Defaults to off."""

    return os.environ.get(_LIVE_ORIGIN_GATE, "").strip() == "1"


def env_summary() -> dict[str, str]:
    """Return a redacted summary of the media-processor env for diagnostics.

    The API key is replaced with ``"***"`` so the function is safe to call
    from operator-side smoke scripts.
    """

    return {
        "live": "1" if is_live_unlocked() else "0",
        "allow_live_origin": "1" if is_live_origin_allowed() else "0",
        "chat_vendor": os.environ.get(_CHAT_VENDOR_ENV, "deepseek"),
        "chat_model": os.environ.get(_CHAT_MODEL_ENV, ""),
        "audio_vendor": os.environ.get(_AUDIO_VENDOR_ENV, "openai"),
        "audio_model": os.environ.get(_AUDIO_MODEL_ENV, ""),
        "endpoint": os.environ.get(_ENDPOINT_ENV, ""),
        "api_key": "***" if os.environ.get(_API_KEY_ENV, "") else "",
    }


__all__ = [
    "ClientFactory",
    "MediaIntegrationPending",
    "MediaVendorRejected",
    "audio_transcriptions",
    "chat_completions",
    "default_client_factory",
    "dispatch_key",
    "env_summary",
    "is_live_origin_allowed",
    "is_live_unlocked",
    "read_prompt_version",
    "resolve_prompt_path",
]
