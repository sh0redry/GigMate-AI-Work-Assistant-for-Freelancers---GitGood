"""Helper coercion from vendor payloads to :class:`WahaMediaResult`.

Splitting the per-vendor coercion out of :mod:`gigmate.media.processor` keeps
that module focused on gates and exception semantics. Both chat-completions
and audio-transcription responses are normalised here into the same proposal
shape so the worker writes one schema regardless of which vendor answered.

Every coercion function is total: it returns either a fully-validated
:class:`WahaMediaResult` or raises :class:`ProcessingUncertain` so the caller
can record the right error code. ``ProcessingUnavailable`` is reserved for
gates and configuration; once a vendor call was attempted, ``Uncertain`` is
the only safe choice.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Mapping

from gigmate.contracts import WahaMediaResult, WahaMediaSegment, WahaMediaSuggestion
from gigmate.media_processing import ProcessingUncertain

log = logging.getLogger(__name__)


_MAX_SEGMENT_TEXT = 4000
_MAX_RESULT_TEXT = 100000


def coerce_chat_response(
    payload: Mapping[str, Any], *, prompt_version: str, vendor: str, model_version: str
) -> WahaMediaResult:
    """Normalise a chat-completions payload into :class:`WahaMediaResult`.

    Accepts both the strict JSON mode body (``choices[0].message.content``
    parsed as a JSON object) and the older plain-text body. Anything that
    cannot be coerced into a valid proposal raises
    :class:`ProcessingUncertain`.
    """

    try:
        message = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProcessingUncertain(f"Vendor response missing message: {exc}") from exc

    parsed: dict[str, Any]
    if isinstance(message, str):
        try:
            parsed = json.loads(message)
        except json.JSONDecodeError as exc:
            raise ProcessingUncertain(f"Vendor content is not JSON: {exc}") from exc
    elif isinstance(message, dict):
        parsed = message
    else:
        raise ProcessingUncertain(f"Vendor message is {type(message).__name__}, expected str/dict")

    return _coerce_proposal(
        parsed, prompt_version=prompt_version, vendor=vendor, model_version=model_version
    )


def coerce_transcription_response(
    payload: Mapping[str, Any], *, prompt_version: str, vendor: str, model_version: str
) -> WahaMediaResult:
    """Normalise an audio-transcription payload into :class:`WahaMediaResult`.

    OpenAI Whisper returns ``{"text": "..."}`` by default and may include a
    ``segments`` array when verbose JSON is requested. Vendors that return a
    richer structure should be normalised before this function is called.
    """

    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ProcessingUncertain("Transcription response has no text")

    segments: list[WahaMediaSegment] = []
    raw_segments = payload.get("segments") or []
    if isinstance(raw_segments, list) and raw_segments:
        for index, raw in enumerate(raw_segments[:200]):
            if not isinstance(raw, dict):
                continue
            snippet = raw.get("text") or raw.get("no_speech_prob") and ""
            if not isinstance(snippet, str) or not snippet:
                continue
            start = raw.get("start")
            end = raw.get("end")
            start_ms = int(round(float(start) * 1000)) if isinstance(start, (int, float)) else None
            end_ms = int(round(float(end) * 1000)) if isinstance(end, (int, float)) else None
            if start_ms is not None and (start_ms < 0 or start_ms > 7_200_000):
                start_ms = None
            if end_ms is not None and (end_ms < 0 or end_ms > 7_200_000):
                end_ms = None
            if start_ms is None or end_ms is None or end_ms <= start_ms:
                start_ms = end_ms = None
            segments.append(
                WahaMediaSegment(
                    text=snippet[:_MAX_SEGMENT_TEXT],
                    page=None,
                    start_ms=start_ms,
                    end_ms=end_ms,
                )
            )
    if not segments:
        segments.append(
            WahaMediaSegment(text=text[:_MAX_SEGMENT_TEXT], page=None, start_ms=None, end_ms=None)
        )

    proposal: dict[str, Any] = {
        "provider": vendor,
        "model_version": model_version,
        "prompt_version": prompt_version,
        "coverage": "complete" if len(segments) == 1 and text else "partial",
        "segments": [s.model_dump(mode="json") for s in segments],
        "summary": text[:4000] if len(segments) == 1 else None,
        "suggestions": [],
        "unresolved_questions": [],
    }
    return _validate(proposal)


# ----------------------------------------------------------- internals


def _coerce_proposal(
    parsed: Mapping[str, Any], *, prompt_version: str, vendor: str, model_version: str
) -> WahaMediaResult:
    if not isinstance(parsed, dict):
        raise ProcessingUncertain("Proposal payload is not an object")

    segments_raw = parsed.get("segments") or []
    if not isinstance(segments_raw, list):
        raise ProcessingUncertain("segments must be a list")
    segments: list[WahaMediaSegment] = []
    for raw in segments_raw[:200]:
        if not isinstance(raw, dict):
            continue
        text = raw.get("text")
        if not isinstance(text, str) or not text:
            continue
        segments.append(
            WahaMediaSegment(
                text=text[:_MAX_SEGMENT_TEXT],
                page=raw.get("page") if isinstance(raw.get("page"), int) else None,
                start_ms=raw.get("start_ms") if isinstance(raw.get("start_ms"), int) else None,
                end_ms=raw.get("end_ms") if isinstance(raw.get("end_ms"), int) else None,
            )
        )
    if not segments:
        raise ProcessingUncertain("Proposal has no readable segments")

    if sum(len(s.text) for s in segments) > _MAX_RESULT_TEXT:
        raise ProcessingUncertain("Vendor proposal exceeded 100000 char limit")

    suggestions: list[WahaMediaSuggestion] = []
    for raw in parsed.get("suggestions") or []:
        if not isinstance(raw, dict):
            continue
        try:
            suggestions.append(WahaMediaSuggestion.model_validate(raw))
        except Exception as exc:  # pragma: no cover - defensive
            log.debug("dropping malformed suggestion: %s", exc)

    unresolved = [str(u) for u in (parsed.get("unresolved_questions") or []) if isinstance(u, str)]
    if len(unresolved) > 30:
        unresolved = unresolved[:30]

    proposal = {
        "provider": vendor,
        "model_version": model_version,
        "prompt_version": prompt_version,
        "coverage": parsed.get("coverage")
        if parsed.get("coverage") in {"complete", "partial", "unknown"}
        else "unknown",
        "segments": [s.model_dump(mode="json") for s in segments],
        "summary": parsed.get("summary") if isinstance(parsed.get("summary"), str) else None,
        "suggestions": [s.model_dump(mode="json") for s in suggestions],
        "unresolved_questions": unresolved,
    }
    return _validate(proposal)


def _validate(proposal: dict[str, Any]) -> WahaMediaResult:
    try:
        return WahaMediaResult.model_validate(proposal)
    except Exception as exc:
        raise ProcessingUncertain(f"WahaMediaResult validation failed: {exc}") from exc


__all__ = [
    "coerce_chat_response",
    "coerce_transcription_response",
]
