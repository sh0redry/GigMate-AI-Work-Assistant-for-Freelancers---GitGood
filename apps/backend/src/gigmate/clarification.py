"""Source-bound AI clarification decisions; never calendar or sending authority.

The model decides what is known, ambiguous, missing or deferred and orders its
questions. Customer facts are quoted verbatim; wording uses a bounded grammar.
An invalid/obsolete assessment is ignored and the existing templates remain usable.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import select

from gigmate.contracts import SourceRef

Item = Literal["date", "start_time", "end_time", "duration", "address"]
ITEMS = {"date", "start_time", "end_time", "duration", "address"}
SCHEDULE_CODES = {
    "missing_schedule",
    "verify_schedule",
    "missing_time",
    "missing_duration",
    "missing_schedule_date",
    "missing_start_time",
    "clarify_date",
    "clarify_start_time",
    "clarify_duration",
}
ADDRESS_CODES = {"missing_address", "verify_address", "clarify_address"}


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source: SourceRef
    quote: Annotated[str, Field(min_length=1, max_length=300)]


class Fact(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    item: Item
    state: Literal["known", "missing", "ambiguous", "deferred"]
    text: Annotated[str, Field(min_length=1, max_length=120)] | None = None
    evidence: Annotated[list[Evidence], Field(max_length=3)] = []

    @model_validator(mode="after")
    def supported(self):
        if self.state == "missing":
            if self.text is not None or self.evidence:
                raise ValueError("Missing facts cannot carry asserted values")
        elif not self.evidence:
            raise ValueError("An assertion requires source evidence")
        if self.state == "known" and not self.text:
            raise ValueError("Known facts require their quoted value")
        if self.text and not any(self.text in e.quote for e in self.evidence):
            raise ValueError("A fact must be quoted, not invented")
        return self


class Assessment(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal["1.0.0"]
    facts: Annotated[list[Fact], Field(min_length=5, max_length=5)]
    # The model chooses order and phrasing style; it cannot insert extra facts,
    # confirmation claims, recipients or execution instructions into a reply.
    questions: Annotated[list[Item], Field(max_length=4)]
    tone: Literal["concise", "friendly"] = "concise"
    language: Literal["zh-Hans", "zh-Hant", "en"] = "zh-Hans"

    @model_validator(mode="after")
    def complete(self):
        facts = {f.item: f for f in self.facts}
        if set(facts) != ITEMS or len(facts) != len(self.facts):
            raise ValueError("Every fact must be considered exactly once")
        required = set(question_items(facts))
        optional = set()
        if not any(facts[k].state in {"known", "deferred"} for k in ("end_time", "duration")):
            # Duration is independent of a missing/ambiguous/deferred start.
            # AI can ask it now or wait, while mandatory gaps stay covered.
            optional.add("duration")
        if not required <= set(self.questions) <= required | optional or len(self.questions) != len(
            set(self.questions)
        ):
            raise ValueError("Questions must cover precisely the unresolved items")
        return self


def question_items(facts):
    result = []
    for name in ("date", "start_time"):
        if facts[name].state in {"missing", "ambiguous"}:
            result.append(name)
    if facts["date"].state == facts["start_time"].state == "known":
        if not any(facts[k].state == "known" for k in ("end_time", "duration")):
            if not any(facts[k].state == "deferred" for k in ("end_time", "duration")):
                result.append("duration")
    if facts["address"].state in {"missing", "ambiguous"}:
        result.append("address")
    return result


def normalize_missing_fields(data):
    """Component-level omissions mean an incomplete schedule, never a new field."""
    suggestion = data.get("new_work_order")
    if not isinstance(suggestion, dict) or not isinstance(suggestion.get("missing_fields"), list):
        return False
    original = suggestion["missing_fields"]
    if not all(isinstance(item, str) for item in original):
        return False
    normalized = list(
        dict.fromkeys(
            "schedule" if item in {"date", "start_time", "end_time", "duration"} else item
            for item in original
        )
    )
    suggestion["missing_fields"] = normalized
    return normalized != original


def request_for_order(request, order_id):
    """Only the selected order may contribute earlier, revalidated fact snippets."""
    from dataclasses import replace

    messages = {(m["message_id"], m["message_revision"]): m for m in request.recent_messages}
    for entry in request.clarification_context:
        if order_id is not None and entry.get("work_order_id") == order_id:
            for message in entry.get("source_snippets", []):
                messages.setdefault((message["message_id"], message["message_revision"]), message)
    return replace(request, recent_messages=tuple(messages.values()))


def parse_assessment(raw, request, target_order_id=None):
    """Strictly bind quotes to the supplied authorized context; no ID rebinding."""
    if raw is None:
        return None
    request = request_for_order(request, target_order_id)
    try:
        supplied = {
            (m["message_id"], m["message_revision"]): m["text"] for m in request.recent_messages
        }
        supplied[(request.message_id, request.message_revision)] = request.message_text or ""
        # A computed end (start + quoted duration), or computed duration (quoted
        # start/end), is not a separately spoken fact. Omit only that derived
        # component when its counterpart is independently source-valid. Never
        # repair a foreign ID, invented quote, date/start or execution field.
        import copy

        raw = copy.deepcopy(raw)
        if isinstance(raw, dict) and isinstance(raw.get("facts"), list):
            by_item = {f.get("item"): f for f in raw["facts"] if isinstance(f, dict)}
            for name, other in (("end_time", "duration"), ("duration", "end_time")):
                fact = by_item.get(name)
                if not isinstance(fact, dict) or fact.get("state") != "known":
                    continue
                try:
                    Fact.model_validate(fact)
                    continue
                except ValidationError:
                    pass
                if set(fact) - {"item", "state", "text", "evidence"}:
                    continue
                counterpart = Fact.model_validate(by_item.get(other))
                if counterpart.state != "known":
                    continue
                own_evidence = [Evidence.model_validate(e) for e in fact.get("evidence", [])]
                all_evidence = [*own_evidence, *counterpart.evidence]
                if (
                    own_evidence
                    and all(
                        e.quote
                        in supplied.get((e.source.message_id, e.source.message_revision), "")
                        for e in all_evidence
                    )
                    and isinstance(fact.get("text"), str)
                    and not any(fact["text"] in e.quote for e in own_evidence)
                ):
                    fact.update(state="missing", text=None, evidence=[])
        value = Assessment.model_validate(raw)
        if value.language != request.output_language:
            return None
        for fact in value.facts:
            for evidence in fact.evidence:
                key = (evidence.source.message_id, evidence.source.message_revision)
                if evidence.quote not in supplied.get(key, ""):
                    return None
        return value.model_dump(mode="json")
    except (ValidationError, KeyError, TypeError):
        return None


def memory_for(db, account_id, conversation, linked):
    """Bounded prior partial facts, not an unbounded chat history or an instruction."""
    import json

    from gigmate.db import MessageRow, Proposal, ProposalDecision
    from gigmate.message_context import source_allowed

    if not conversation.allowlisted or conversation.account_id != account_id:
        return ()
    result, seen, size = [], set(), 0
    rows = db.scalars(
        select(Proposal)
        .where(
            Proposal.account_id == account_id,
            Proposal.conversation_id == conversation.id,
            Proposal.context_version <= conversation.context_version,
        )
        .order_by(Proposal.created_at.desc(), Proposal.id.desc())
        .limit(20)
    )
    for row in rows:
        order_id = row.work_order_id
        if order_id is None:
            decision = db.get(ProposalDecision, row.event_id)
            if decision and decision.account_id == account_id and decision.proposal_id == row.id:
                order_id = decision.work_order_id
        if order_id not in linked or order_id in seen or not row.clarification:
            continue
        seen.add(order_id)
        try:
            assessment = Assessment.model_validate(row.clarification["assessment"])
        except (ValidationError, KeyError, TypeError):
            continue
        snippets, valid = {}, True
        for fact in assessment.facts:
            for evidence in fact.evidence:
                ref = evidence.source
                message = db.scalar(
                    select(MessageRow)
                    .where(
                        MessageRow.id == ref.message_id,
                        MessageRow.account_id == account_id,
                        MessageRow.conversation_id == conversation.id,
                    )
                    .order_by(MessageRow.revision.desc())
                )
                if (
                    message is None
                    or message.revision != ref.message_revision
                    or message.data.get("revoked")
                    or message.data.get("direction") != "incoming"
                    or message.data.get("source") != "app"
                    or evidence.quote not in (message.data.get("text") or "")
                ):
                    valid = False
                    break
                if not source_allowed(db, conversation, message):
                    valid = False
                    break
                key = (ref.message_id, ref.message_revision)
                snippet = snippets.setdefault(
                    key,
                    {
                        "message_id": ref.message_id,
                        "message_revision": ref.message_revision,
                        "text": "",
                        "occurred_at": message.data["occurred_at"],
                        "_start": len(message.data["text"]),
                        "_end": 0,
                    },
                )
                position = message.data["text"].index(evidence.quote)
                snippet["_start"] = min(snippet["_start"], position)
                snippet["_end"] = max(snippet["_end"], position + len(evidence.quote))
                snippet["text"] = message.data["text"][snippet["_start"] : snippet["_end"]]
        if not valid:
            continue
        for snippet in snippets.values():
            snippet.pop("_start")
            snippet.pop("_end")
        entry = {
            "work_order_id": order_id,
            "facts": assessment.model_dump(mode="json")["facts"],
            "source_snippets": list(snippets.values()),
        }
        cost = len(json.dumps(entry, ensure_ascii=False).encode())
        if len(result) >= 3 or size + cost > 5000:
            break
        result.append(entry)
        size += cost
    return tuple(result)


def field_for_code(code):
    if code in SCHEDULE_CODES:
        return "schedule"
    if code in ADDRESS_CODES:
        return "address"
    return None


def current_assessment(db, account_id, order, conversation):
    """Find only a current, owned, source-valid and explicitly assigned proposal."""
    from gigmate.db import Inbox, MessageRow, Proposal, ProposalDecision
    from gigmate.message_context import source_allowed

    if not conversation.allowlisted or conversation.account_id != account_id:
        return None
    rows = db.scalars(
        select(Proposal)
        .where(
            Proposal.account_id == account_id,
            Proposal.conversation_id == conversation.id,
            Proposal.context_version <= conversation.context_version,
        )
        .order_by(Proposal.created_at.desc(), Proposal.id.desc())
        .limit(10)
    )
    for row in rows:
        if not row.clarification:
            continue
        if row.context_version != conversation.context_version:
            later = list(
                db.scalars(
                    select(Inbox).where(
                        Inbox.account_id == account_id,
                        Inbox.payload["conversation_id"].as_string() == conversation.id,
                        Inbox.context_version > row.context_version,
                    )
                )
            )
            # Own API echoes carry no new customer intent. Any other context
            # advance requires fresh analysis, including manual authorization.
            if (
                not later
                or max(i.context_version for i in later) != conversation.context_version
                or any(
                    i.payload.get("direction") != "outgoing" or i.payload.get("source") != "api"
                    for i in later
                )
            ):
                continue
        assigned = row.work_order_id == order.id
        if not assigned:
            decision = db.get(ProposalDecision, row.event_id)
            assigned = bool(
                decision
                and decision.account_id == account_id
                and decision.proposal_id == row.id
                and decision.work_order_id == order.id
            )
        if not assigned:
            continue
        try:
            value = Assessment.model_validate(row.clarification["assessment"])
        except (ValidationError, KeyError, TypeError):
            continue
        good = True
        sources = {}
        for fact in value.facts:
            for evidence in fact.evidence:
                ref = evidence.source
                latest = db.scalar(
                    select(MessageRow)
                    .where(
                        MessageRow.id == ref.message_id,
                        MessageRow.account_id == account_id,
                        MessageRow.conversation_id == conversation.id,
                    )
                    .order_by(MessageRow.revision.desc())
                )
                if (
                    latest is None
                    or latest.revision != ref.message_revision
                    or latest.data.get("revoked")
                    or latest.data.get("direction") != "incoming"
                    or latest.data.get("source") != "app"
                    or evidence.quote not in (latest.data.get("text") or "")
                    or not source_allowed(db, conversation, latest)
                ):
                    good = False
                    break
                sources[(ref.message_id, ref.message_revision)] = ref.model_dump(mode="json")
        if good:
            return value, row, list(sources.values())
    return None


def reply_plan(db, account_id, order, conversation, fallback_items, fallback_questions):
    """Derive a review-only reply; leave formal facts and original calendar intact."""
    found = current_assessment(db, account_id, order, conversation)
    if not found:
        return None
    assessment, proposal, sources = found
    facts = {f.item: f for f in assessment.facts}
    fields = order.data["fields"]
    basis = proposal.clarification.get("basis", {})
    if proposal.work_order_id is None:
        from gigmate.db import CommandResult

        adopted = db.scalar(
            select(CommandResult).where(
                CommandResult.account_id == account_id,
                CommandResult.scope == "create_work_order",
                CommandResult.data["id"].as_string() == order.id,
            )
        )
        if adopted is not None:
            basis = adopted.data.get("fields", {})
    schedule = fields["schedule"]
    address = fields["address"]
    # Accepted/manual complete facts take precedence. An unaccepted partial
    # amendment remains separate from the original confirmed calendar interval.
    amend = any(c.get("field") == "schedule" for c in proposal.changes)
    same_basis = all(
        schedule.get(k) == basis.get("schedule", {}).get(k) for k in ("value", "status")
    )
    date_only = isinstance(schedule["value"], dict) and schedule["value"].get("kind") == "date_only"
    same_generation = (
        order.data["version"] == proposal.base_work_order_version
        or proposal.work_order_id is None
        and order.data["version"] == 1
    )
    retained_date = date_only and (same_generation or same_basis) and facts["date"].state == "known"
    use_schedule = not schedule["value"] or (amend and same_basis) or retained_date
    if schedule["status"] == "confirmed" and not amend and not date_only:
        use_schedule = False
    if (
        proposal.base_work_order_version
        and order.data["version"] != proposal.base_work_order_version
    ):
        if not same_basis:
            use_schedule = False
    address_amend = any(c.get("field") == "address" for c in proposal.changes)
    address_basis = all(
        address.get(k) == basis.get("address", {}).get(k) for k in ("value", "status")
    )
    use_address = (
        not address["value"]
        or address["status"] == "needs_review"
        or address_amend
        and address_basis
        or address["status"] != "confirmed"
        and facts["address"].state in {"ambiguous", "deferred"}
    )
    if (
        proposal.base_work_order_version
        and order.data["version"] != proposal.base_work_order_version
        and not address_basis
        and address["value"]
    ):
        use_address = False
    deferred = order.data.get("deferred") or {}
    use_schedule = use_schedule and "schedule" not in deferred
    use_address = use_address and "address" not in deferred
    if not use_schedule and not use_address:
        return None
    language = assessment.language
    en = language == "en"
    echoes = []
    if use_schedule:
        for name in ("date", "start_time"):
            if facts[name].state == "known":
                echoes.append(facts[name].text)
    if use_address and facts["address"].state == "known":
        echoes.append(facts["address"].text)
    items, questions = [], []
    for name in assessment.questions:
        if (name == "address" and not use_address) or (name != "address" and not use_schedule):
            continue
        ambiguous = facts[name].state == "ambiguous"
        code = {
            "date": "missing_schedule_date",
            "start_time": "missing_start_time",
            "duration": "missing_duration",
            "address": "missing_address",
        }[name]
        if ambiguous:
            code = "clarify_" + name
        text = {
            "date": "Which date do you mean?" if en else "请问具体是哪一天？",
            "start_time": "What start time do you mean?" if en else "请问具体几点开始？",
            "duration": "How long will it last, or what time will it end?"
            if en
            else "请问预计持续多久，或到几点结束？",
            "address": "What is the meeting address?" if en else "请问具体见面地址是？",
        }[name]
        if language == "zh-Hant":
            text = {
                "date": "請問具體是哪一天？",
                "start_time": "請問具體幾點開始？",
                "duration": "請問預計持續多久，或到幾點結束？",
                "address": "請問具體見面地址是？",
            }[name]
        if name == "duration" and facts["start_time"].state != "known":
            text = (
                "How long will the service take?"
                if en
                else "請問預計需要多長時間？"
                if language == "zh-Hant"
                else "请问预计需要多长时间？"
            )
        if ambiguous:
            quote = facts[name].text
            text = (
                (
                    f"Could you clarify what you mean by '{quote}'?"
                    if en
                    else f"你提到「{quote}」，请问具体是指什么？"
                )
                if quote
                else text
            )
            if quote and language == "zh-Hant":
                text = f"你提到「{quote}」，請問具體是指甚麼？"
        items.append(code)
        questions.append(text)
    # Reason codes and sentences are not one-to-one (a date-only confirmation
    # has two codes in one sentence). Preserve field groups, never zip them.
    address_count = int(any(field_for_code(c) == "address" for c in fallback_items))
    for field, used in (("schedule", use_schedule), ("address", use_address)):
        if used:
            continue
        items.extend(c for c in fallback_items if field_for_code(c) == field)
        if field == "address" and address_count:
            questions.extend(fallback_questions[-1:])
        elif field == "schedule":
            questions.extend(fallback_questions[:-1] if address_count else fallback_questions)
    if not items:
        return [], "", sources
    echo = (
        (
            "You mentioned " + ", ".join(echoes) + ". "
            if en
            else "你提到「" + "、".join(echoes) + "」。"
        )
        if echoes
        else ""
    )
    intro = (
        ("Thanks for the details. " if en else "谢谢说明。")
        if assessment.tone == "friendly"
        else ""
    )
    return items, intro + echo + (" ".join(questions) if en else "".join(questions)), sources
