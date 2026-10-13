"""MIME-based routing table for the media processor.

A owns the canonical whitelist (see ``gigmate.waha_media.MAX_BYTES`` and the
``accepted_types`` field on :class:`gigmate.contracts.WahaMediaCapabilities`).
B only needs to know which vendor adapter handles each accepted type so that
an unexpected MIME never silently falls back to a fake result.
"""

from __future__ import annotations

from typing import Final

# Image / OCR -> chat-completions with a vision-capable model.
OCR_MIMETYPES: Final[frozenset[str]] = frozenset({"image/png", "image/jpeg", "image/webp"})

# Audio / ASR -> audio-transcription endpoint.
ASR_MIMETYPES: Final[frozenset[str]] = frozenset(
    {"audio/ogg", "audio/mpeg", "audio/wav", "audio/mp4", "audio/x-m4a"}
)

# PDF -> chat-completions with a document-aware model.
PDF_MIMETYPES: Final[frozenset[str]] = frozenset({"application/pdf"})

# Plain text -> chat-completions (or simple extraction).
TEXT_MIMETYPES: Final[frozenset[str]] = frozenset({"text/plain"})


def route(mimetype: str) -> str:
    """Return the dispatch key for ``mimetype``.

    The returned key matches :func:`gigmate.media.llm.dispatch` and is one of
    ``"ocr"``, ``"asr"``, ``"pdf"``, ``"text"`` or ``"unsupported"``. Callers
    must handle ``"unsupported"`` explicitly; this function never raises so the
    processor can render the refusal into a clear :class:`WahaMediaResult`
    instead of crashing the worker.
    """
    if mimetype in OCR_MIMETYPES:
        return "ocr"
    if mimetype in ASR_MIMETYPES:
        return "asr"
    if mimetype in PDF_MIMETYPES:
        return "pdf"
    if mimetype in TEXT_MIMETYPES:
        return "text"
    return "unsupported"


__all__ = [
    "ASR_MIMETYPES",
    "OCR_MIMETYPES",
    "PDF_MIMETYPES",
    "TEXT_MIMETYPES",
    "route",
]
