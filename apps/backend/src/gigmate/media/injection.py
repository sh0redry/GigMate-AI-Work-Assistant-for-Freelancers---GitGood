"""Instruction-text detection for media attachments (Role B).

Media content is attacker-controlled. An image can carry instructions as
pixels, an audio clip can carry them as speech, and a PDF can carry them in a
white-on-white or otherwise hidden text layer — all of it reaches the model
as *content*, and none of it is ever a command to this system. The vendor
answer is equally untrusted: a fooled model returns the instruction in its
``summary`` / ``suggestions`` / ``unresolved_questions`` so that the next
stage reads it as an operator decision.

This module is the pure half of that boundary. It never raises, never calls a
vendor and never rewrites content: it classifies text and returns stable
markers that :mod:`gigmate.media.coercion` attaches to the
:class:`gigmate.contracts.WahaMediaResult` so a reviewer can see that the
result is tainted. Nothing here grants, removes or infers authority —
:class:`gigmate.contracts.WahaMediaEvidence.business_confirmation_required`
stays ``True`` regardless of what an attachment claims, and the marker only
decides how loudly the result is flagged.

The patterns are deliberately narrow and bilingual (the product faces
Cantonese/Chinese and English merchants), and the suite in
``contracts/evaluation/media_injection.json`` pairs every attack with clean
control cases so over-flagging is caught by the same tests that catch
under-flagging. A marker costs a human a second look; a missed instruction
costs a wrong work order, so the bias is to flag.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Iterable, Mapping

log = logging.getLogger(__name__)

#: Stable prefix for every marker. A marker is ``<prefix>:<field>`` so a
#: reviewer can tell *where* the instruction-shaped text was found without
#: reading the payload.
MARKER_PREFIX = "media:instruction-text-detected"

# (pattern id, compiled pattern). Ids are stable and appear in logs; the
# patterns are data, not code paths, and are matched case-insensitively.
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "ignore_previous_instructions",
        re.compile(
            r"忽略(以上|之前|上述|前面)(的)?(所有)?(指示|指令|规则|要求)"
            r"|ignore\s+(all\s+)?(previous|prior|above|earlier)\s+"
            r"(instructions|prompts|rules)",
            re.IGNORECASE,
        ),
    ),
    (
        "role_override",
        re.compile(
            r"(you\s+are\s+now|act\s+as|pretend\s+to\s+be|from\s+now\s+on\s+you)"
            r"|(你现在是|请扮演|从现在开始你是|以系统身份)"
            r"|(system|developer)\s*(prompt|message)?\s*[:：]",
            re.IGNORECASE,
        ),
    ),
    (
        "authority_claim",
        re.compile(
            r"(mark|set|flag)\s+(this|the\s+\w+)?\s*as\s+"
            r"(confirmed|approved|completed|verified)"
            r"|(标记|标注|设定|设置|视为)\s*(为)?\s*(已)?(确认|完成|核准|批准)"
            r"|business_confirmation_required\s*[:=]\s*false"
            r"|consent_(download|model)\s*[:=]\s*false",
            re.IGNORECASE,
        ),
    ),
    (
        "review_bypass",
        re.compile(
            r"skip\s+(the\s+)?(review|confirmation|approval|human)"
            r"|(no|without)\s+(need\s+for|further)\s+(review|confirmation|approval)"
            r"|(跳过|绕过|不需要|无需|不必)\s*(人工)?\s*(复核|审核|确认|审批|复查)",
            re.IGNORECASE,
        ),
    ),
    (
        "prompt_exfiltration",
        re.compile(
            r"(reveal|print|repeat|output|leak)\s+(your|the)\s+"
            r"(system\s+)?(prompt|instructions|rules)"
            r"|(输出|显示|泄露|重复)\s*(你的|系统)?\s*(提示词|提示|指令|规则)",
            re.IGNORECASE,
        ),
    ),
    (
        "instruction_verb",
        re.compile(
            r"execute\s+the\s+following|follow\s+these\s+instructions"
            r"|disregard\s+(all|any)\s+"
            r"|(请|必须|务必|立即)\s*(严格)?\s*(执行|遵循|遵守)(以下|下列)?",
            re.IGNORECASE,
        ),
    ),
)


def scan_text(text: str | None) -> tuple[str, ...]:
    """Return the ids of every instruction-shaped pattern found in ``text``.

    Total: empty or ``None`` input yields an empty tuple. The text itself is
    never returned — only stable pattern ids — so a marker can be logged and
    stored without echoing the payload.
    """

    if not text:
        return ()
    return tuple(name for name, pattern in _PATTERNS if pattern.search(text))


@dataclass(frozen=True)
class MediaInjectionAssessment:
    """What instruction-shaped text was found, and where."""

    detected: bool
    markers: tuple[str, ...]
    pattern_ids: tuple[str, ...]
    fields: tuple[str, ...]

    @property
    def note(self) -> str | None:
        """Single stable code for logs; ``None`` when nothing was found."""

        return MARKER_PREFIX if self.detected else None


def marker(field: str) -> str:
    """Build the stable marker for a field name."""

    return f"{MARKER_PREFIX}:{field}"


def assess(
    *,
    caption: str | None = None,
    segments: Iterable[object] = (),
    summary: str | None = None,
    suggestions: Iterable[object] = (),
    unresolved: Iterable[object] = (),
    transcript: str | None = None,
) -> MediaInjectionAssessment:
    """Classify every untrusted text surface of one media result.

    ``segments`` may be :class:`gigmate.contracts.WahaMediaSegment` objects or
    plain strings; ``suggestions`` may be
    :class:`gigmate.contracts.WahaMediaSuggestion` objects or plain strings.
    Each surface contributes its own field marker, so a tainted summary is
    distinguishable from a tainted page.
    """

    hits: dict[str, tuple[str, ...]] = {}
    for field, value in (
        ("caption", caption),
        ("transcript", transcript),
        ("summary", summary),
    ):
        found = scan_text(value)
        if found:
            hits[field] = found

    for field, values in (
        ("segment", segments),
        ("suggestion", suggestions),
        ("unresolved", unresolved),
    ):
        for item in values:
            text = _text_of(item)
            found = scan_text(text)
            if found:
                hits[field] = tuple(sorted(set(hits.get(field, ()) + found)))

    if not hits:
        return MediaInjectionAssessment(detected=False, markers=(), pattern_ids=(), fields=())

    fields = tuple(sorted(hits))
    pattern_ids = tuple(sorted({name for ids in hits.values() for name in ids}))
    return MediaInjectionAssessment(
        detected=True,
        markers=tuple(marker(field) for field in fields),
        pattern_ids=pattern_ids,
        fields=fields,
    )


def _text_of(item: object) -> str | None:
    """Read the text of a segment / suggestion object, dict or bare string.

    The coercion layer scans raw vendor payloads, so a mapping with a
    ``text`` key is as common here as a validated model object.
    """

    if isinstance(item, str):
        return item
    if isinstance(item, Mapping):
        text = item.get("text")
        return text if isinstance(text, str) else None
    text = getattr(item, "text", None)
    return text if isinstance(text, str) else None


def log_assessment(assessment: MediaInjectionAssessment) -> None:
    """Emit one structured line for a detected assessment.

    Only pattern ids and field names are logged; never the payload.
    """

    if not assessment.detected:
        return
    log.warning(
        "MEDIA_INJECTION_DETECTED fields=%s patterns=%s",
        ",".join(assessment.fields),
        ",".join(assessment.pattern_ids),
    )


__all__ = [
    "MARKER_PREFIX",
    "MediaInjectionAssessment",
    "assess",
    "log_assessment",
    "marker",
    "scan_text",
]
