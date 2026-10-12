"""Real PDF page extraction for the media processor seam.

Role A's ingestion gate validates the ``%PDF-`` signature and the 20 MiB
size bound, but explicitly documents that this is *not* a parser; B must
enforce parser/page limits before model use. This module is that parser:
it turns PDF bytes into verbatim per-page text with bounded I/O so the
processor can build page-addressable :class:`WahaMediaResult` segments.

Every refusal below happens **before** any vendor request is submitted,
so the processor maps :class:`PdfParseError` to
:class:`gigmate.media_processing.ProcessingUnavailable` — never to
``ProcessingUncertain``. Nothing in this module is truncated silently: a
document that exceeds a bound is refused with a distinct code instead of
being quietly cut down.

Bounds (aligned with the ``WahaMediaResult`` contract in
:mod:`gigmate.contracts`):

* pages — at most 200 (``WahaMediaSegment.page`` is 1..200 and
  ``segments`` is capped at 200 entries).
* page text — split into chunks of at most 4000 characters
  (``WahaMediaSegment.text`` max length); a long page becomes several
  segments that share the same page number.
* segments — at most 200 after splitting. While the total-text bound is
  100000, this check is defensive: more than 200 chunks of at most 4000
  characters each always implies more than 100000 characters of text, so
  the text bound refuses first. It stays in place to keep the parser safe
  if a bound is ever relaxed independently.
* total text — at most 100000 characters (``WahaMediaResult`` validator).
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)

MAX_PAGES = 200
MAX_SEGMENT_TEXT = 4000
MAX_SEGMENTS = 200
MAX_TOTAL_TEXT = 100_000


class PdfParseError(RuntimeError):
    """Raised when the bytes cannot be turned into bounded page text.

    The message is a stable ``MEDIA_PDF_*`` error code (optionally with
    detail) so the worker can persist it verbatim.
    """


@dataclass(frozen=True)
class PdfPageText:
    """Verbatim text of a single PDF page, 1-based page number."""

    page: int
    text: str


@dataclass(frozen=True)
class PdfExtraction:
    """Bounded extraction result handed to the business-extraction pass.

    ``total_pages`` and ``empty_pages`` let the processor surface an
    honest unresolved question when part of the document carries no text
    layer (e.g. a scanned annex inside a text PDF) instead of pretending
    the extraction covered everything.
    """

    pages: list[PdfPageText]
    total_pages: int
    empty_pages: int


def extract(content: bytes) -> PdfExtraction:
    """Parse ``content`` and return bounded per-page text.

    Raises :class:`PdfParseError` (stable ``MEDIA_PDF_*`` code) when the
    bytes are not a readable PDF, the page count exceeds the contract
    bound, the split would exceed the segment bound, the total text
    exceeds the contract bound, or no page carries any text layer.
    """

    try:
        from pypdf import PdfReader
    except ImportError:  # pragma: no cover - dependency is in requirements.lock
        raise PdfParseError("MEDIA_PDF_PARSER_LIBRARY_MISSING") from None

    try:
        reader = PdfReader(io.BytesIO(content))
        total_pages = len(reader.pages)
    except Exception as exc:
        log.info("MEDIA_PDF_NOT_PARSEABLE: %s", type(exc).__name__)
        raise PdfParseError(f"MEDIA_PDF_NOT_PARSEABLE: {type(exc).__name__}") from None

    if total_pages < 1:
        raise PdfParseError("MEDIA_PDF_NOT_PARSEABLE: no pages")
    if total_pages > MAX_PAGES:
        # Refuse rather than silently process a prefix of the document.
        raise PdfParseError(f"MEDIA_PDF_PAGE_LIMIT: {total_pages} > {MAX_PAGES}")

    pages: list[PdfPageText] = []
    empty_pages = 0
    total_text = 0
    for index, page in enumerate(reader.pages, start=1):
        try:
            raw = page.extract_text() or ""
        except Exception:  # one unreadable page must not fake coverage
            log.info("MEDIA_PDF page %s unreadable", index)
            raw = ""
        text = raw.strip()
        if not text:
            empty_pages += 1
            continue
        total_text += len(text)
        pages.append(PdfPageText(page=index, text=text))

    if not pages:
        # Scanned/image-only PDFs have no text layer; silently shipping them
        # to a text model would fabricate an extraction. Refuse explicitly.
        raise PdfParseError("MEDIA_PDF_NO_TEXT_LAYER")
    if total_text > MAX_TOTAL_TEXT:
        raise PdfParseError(f"MEDIA_PDF_TEXT_LIMIT: {total_text} > {MAX_TOTAL_TEXT}")
    if len(pages) > MAX_SEGMENTS:
        raise PdfParseError(f"MEDIA_PDF_SEGMENT_LIMIT: {len(pages)} > {MAX_SEGMENTS}")

    split: list[PdfPageText] = []
    for item in pages:
        for offset in range(0, len(item.text), MAX_SEGMENT_TEXT):
            split.append(
                PdfPageText(page=item.page, text=item.text[offset : offset + MAX_SEGMENT_TEXT])
            )
    if len(split) > MAX_SEGMENTS:
        raise PdfParseError(f"MEDIA_PDF_SEGMENT_LIMIT: {len(split)} > {MAX_SEGMENTS}")
    return PdfExtraction(pages=split, total_pages=total_pages, empty_pages=empty_pages)


__all__ = [
    "MAX_PAGES",
    "MAX_SEGMENTS",
    "MAX_SEGMENT_TEXT",
    "MAX_TOTAL_TEXT",
    "PdfExtraction",
    "PdfPageText",
    "PdfParseError",
    "extract",
]
