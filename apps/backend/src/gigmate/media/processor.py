"""Real-model :class:`MediaProcessor` implementation for the WAHA seam.

This module is the production-shaped B-side implementation loaded by
:func:`gigmate.media_processing.processor` when ``GIGMATE_MEDIA_PROCESSOR_FACTORY``
points at :class:`MediaProcessorImpl`. It mirrors the two-gate safety pattern
used by :class:`gigmate.extraction.llm.LLMProvider`:

1. Module-level :data:`_ENABLED` flag. While ``False`` (the shipping default)
   the processor refuses every call with
   :class:`gigmate.media_processing.ProcessingUnavailable` *before* it reads
   any environment variable. The flag must be flipped by editing this file;
   the operator switch alone is never enough to enable real calls.
2. ``GIGMATE_MEDIA_LIVE=1`` operator switch. Even after the class flag is
   flipped, the processor refuses every call unless this variable is exported.

The processor only returns :class:`WahaMediaResult` proposals. Merchant
confirmation is enforced downstream by
:class:`gigmate.contracts.WahaMediaEvidence.business_confirmation_required`; B
never marks a field ``confirmed`` and never grants execution authority.

Exception semantics:

* :class:`ProcessingUnavailable` — no vendor request was submitted. Used when
  the gates are closed, the vendor is unrecognised, the prompt is malformed,
  the MIME is unsupported or the API key is missing.
* :class:`ProcessingUncertain` — the vendor call may have been submitted
  (charged). Used for 4xx / 5xx, schema failures, timeouts, and for the ASR
  path when only DeepSeek credentials are configured. The worker must use
  :meth:`reconcile` rather than automatic resubmission.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from gigmate.contracts import WahaMediaResult
from gigmate.media_processing import (
    MediaInput,
    MediaProcessor,
    ProcessingUnavailable,
    ProcessingUncertain,
)

from . import llm
from .coercion import coerce_chat_response, coerce_transcription_response
from .routing import route

log = logging.getLogger(__name__)

# Two-gate safety flag. While False the processor refuses every call before
# reading any environment variable. The flag must be flipped by editing this
# module; the operator switch alone is never sufficient.
_ENABLED = False


class MediaProcessorImpl:
    """Production-shaped media processor for the WAHA ingestion seam.

    The instance is constructed without arguments because the factory in
    :mod:`gigmate.media_processing` calls the class with no arguments.
    Configuration is read on every call so a long-running worker picks up
    operator changes without a restart.
    """

    name = "media-llm"
    prompt_path: Path

    def __init__(self) -> None:
        self.prompt_path = llm.resolve_prompt_path()

    # --------------------------------------------------------------- gates

    @staticmethod
    def _gates_open() -> None:
        if not _ENABLED:
            raise ProcessingUnavailable(
                "gigmate.media.processor._ENABLED is False; flip the seam flag "
                "in apps/backend/src/gigmate/media/processor.py before exporting "
                "GIGMATE_MEDIA_LIVE=1."
            )
        if not llm.is_live_unlocked():
            raise ProcessingUnavailable(
                "GIGMATE_MEDIA_LIVE is not '1'; refusing to call the vendor "
                "until the operator explicitly enables live media processing."
            )
        if not llm.env_summary()["api_key"]:
            raise ProcessingUnavailable(
                "GIGMATE_MEDIA_API_KEY is empty; refusing the call rather than "
                "silently falling back to a fabricated result."
            )

    @staticmethod
    def _check_origin(request: MediaInput) -> None:
        if request.origin not in {"synthetic", "live"}:
            raise ProcessingUnavailable("MEDIA_ORIGIN_INVALID")
        if request.origin == "live" and not llm.is_live_origin_allowed():
            raise ProcessingUnavailable(
                "Live-origin media is refused by default; export "
                "GIGMATE_MEDIA_ALLOW_LIVE_ORIGIN=1 to permit real customer "
                "attachments to reach the model."
            )

    # ------------------------------------------------------------ prompts

    def _prompt_version(self) -> str:
        version = llm.read_prompt_version(self.prompt_path)
        if version == llm._PROMPT_VERSION_PENDING:
            raise ProcessingUnavailable(
                f"Prompt file {self.prompt_path} is missing or malformed; "
                "cannot call the vendor with an unversioned prompt."
            )
        return version

    # ------------------------------------------------------------- public

    def process(self, request: MediaInput) -> WahaMediaResult:
        self._gates_open()
        self._check_origin(request)
        prompt_version = self._prompt_version()

        dispatch = route(request.mimetype)
        if dispatch == "unsupported":
            raise ProcessingUnavailable(
                f"MIME {request.mimetype!r} is not accepted by the WAHA media "
                "seam; refused without contacting the vendor."
            )

        if dispatch == "pdf":
            raise ProcessingUnavailable("MEDIA_PDF_PARSER_PENDING")
        try:
            vendor = (
                llm._resolve_audio_vendor() if dispatch == "asr" else llm._resolve_chat_vendor()
            )
            llm._resolve_chat_endpoint(vendor)
        except llm.MediaIntegrationPending as exc:
            raise ProcessingUnavailable(str(exc)) from None
        if dispatch == "ocr" and vendor == "deepseek":
            raise ProcessingUnavailable("MEDIA_VISION_VENDOR_UNVERIFIED")
        if dispatch == "text":
            try:
                text = request.content.decode("utf-8")
            except UnicodeError:
                raise ProcessingUnavailable("MEDIA_TEXT_ENCODING_INVALID") from None
            if len(text) > 90000:
                raise ProcessingUnavailable("MEDIA_TEXT_CHUNKING_PENDING")

        try:
            client = llm.default_client_factory(timeout=30.0)
        except Exception as exc:  # pragma: no cover - httpx import error
            raise ProcessingUnavailable(f"Cannot build HTTP client: {exc}") from exc

        try:
            if dispatch == "asr":
                return self._process_asr(request, client, prompt_version)
            return self._process_chat(request, client, prompt_version, dispatch)
        except ProcessingUnavailable:
            raise
        except llm.MediaIntegrationPending as exc:
            raise ProcessingUnavailable(str(exc)) from exc
        except llm.MediaVendorRejected as exc:
            log.warning("MEDIA_VENDOR_REJECTED")
            raise ProcessingUncertain("MEDIA_VENDOR_REJECTED") from exc
        except Exception as exc:
            # Network errors, JSON decode errors and any other unexpected
            # failure: the request may have incurred cost, so reconcile
            # rather than retry.
            log.warning("MEDIA_VENDOR_RESULT_UNKNOWN")
            raise ProcessingUncertain("MEDIA_VENDOR_RESULT_UNKNOWN") from exc

        finally:
            close = getattr(client, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    log.warning("MEDIA_CLIENT_CLOSE_FAILED")

    # ------------------------------------------------------------ per-vendor

    def _process_chat(
        self,
        request: MediaInput,
        client,
        prompt_version: str,
        _dispatch: str,
    ) -> WahaMediaResult:
        chat_vendor = llm._resolve_chat_vendor()
        chat_model = os.environ.get(llm._CHAT_MODEL_ENV, "").strip() or None
        endpoint = llm._resolve_chat_endpoint(chat_vendor)
        model = chat_model or self._default_chat_model(chat_vendor)
        model_version = llm._chat_model_version(chat_vendor, model)
        prompt = self._prompt_text()
        payload = llm.chat_completions(
            client=client,
            endpoint=endpoint,
            model=model,
            prompt=prompt,
            mimetype=request.mimetype,
            content=request.content,
            caption=request.caption,
        )
        return coerce_chat_response(
            payload, prompt_version=prompt_version, vendor=self.name, model_version=model_version
        )

    def _process_asr(
        self,
        request: MediaInput,
        client,
        prompt_version: str,
    ) -> WahaMediaResult:
        audio_vendor = llm._resolve_audio_vendor()
        audio_model = os.environ.get(llm._AUDIO_MODEL_ENV, "").strip() or None
        endpoint = llm._resolve_chat_endpoint(audio_vendor)
        model = audio_model or "whisper-1"
        model_version = llm._audio_model_version(audio_vendor, model)
        payload = llm.audio_transcriptions(
            client=client,
            endpoint=endpoint,
            model=model,
            mimetype=request.mimetype,
            content=request.content,
            caption=request.caption,
        )
        return coerce_transcription_response(
            payload, prompt_version=prompt_version, vendor=self.name, model_version=model_version
        )

    def _default_chat_model(self, vendor: str) -> str:
        if vendor == "deepseek":
            return "deepseek-chat"
        if vendor == "openai":
            return "gpt-4o-mini"
        return "custom-model"

    def _prompt_text(self) -> str:
        try:
            return self.prompt_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise ProcessingUnavailable(
                f"Cannot read prompt file {self.prompt_path}: {exc}"
            ) from exc

    # ------------------------------------------------------------ reconcile

    def reconcile(self, request_id: str) -> WahaMediaResult | None:
        """Read-only vendor lookup; never resubmit.

        Vendor APIs do not generally expose a stable ``request_id`` based
        lookup for chat-completions, so the default behaviour is to return
        ``None``. Operators can extend this module with a vendor-specific
        lookup (e.g. DeepSeek's request-id echo) once the seam flag is
        flipped and the operator switch is on.
        """

        if not _ENABLED or not llm.is_live_unlocked():
            return None
        return None


# ------------------------------------------------------------- builder


def build_processor() -> MediaProcessor:
    """Factory entry point referenced by ``GIGMATE_MEDIA_PROCESSOR_FACTORY``.

    The factory string format is ``"module:AttrName"``; this module is
    referenced as ``gigmate.media.processor:MediaProcessorImpl``.
    """

    return MediaProcessorImpl()


# Defensive: re-export the configured default so tests can introspect it
# without reaching into the module-private constant.
def is_seam_enabled() -> bool:
    return _ENABLED


__all__ = [
    "MediaProcessorImpl",
    "build_processor",
    "is_seam_enabled",
]
