"""Field-local validation after envelope/provenance checks, never execution authority."""

from pydantic import ValidationError

from gigmate.contracts import NewWorkOrderSuggestedField, ProposalChange

FIELDS = {"schedule", "address", "summary", "quantity", "specification", "deadline"}


def retain_valid_fields(data, *, time_basis_available=True):
    """Drop an unusable field, preserving unrelated sourced information.

    Unknown objects are not stringified into addresses or descriptions. Source
    and envelope failures must have already been refused by the caller.
    """
    original_changes = data.get("changes")
    original_questions = list(data.get("unresolved_questions") or [])
    notes = []
    if data.get("unresolved_questions") is None:
        data["unresolved_questions"] = []
    data["unresolved_questions"] = [
        q for q in data["unresolved_questions"] if isinstance(q, str) and q.strip()
    ]
    questions = data["unresolved_questions"]
    changes = []
    for item in data.get("changes") or []:
        field = item.get("field") if isinstance(item.get("field"), str) else "unknown"
        try:
            if (
                field in {"schedule", "deadline"}
                and not time_basis_available
                and item.get("new_value") is not None
            ):
                raise ValueError("Missing time basis")
            validate_field_value(field, item.get("new_value"), partial_schedule=True)
            ProposalChange.model_validate(item)
        except (ValidationError, ValueError):
            notes.append("llm:field-omitted:" + (field if field in FIELDS else "unknown"))
            if field in {"schedule", "deadline"} and not time_basis_available:
                notes.append("llm:time-basis-missing")
            if field in FIELDS:
                questions.append(f"请核对{FIELD_LABELS[field]}，其余已识别内容仍保留。")
        else:
            changes.append(item)
    data["changes"] = changes
    suggestion = data.get("new_work_order")
    if suggestion:
        valid = []
        missing = [
            field
            for field in suggestion.get("missing_fields") or []
            if isinstance(field, str) and field in FIELDS
        ]
        open_questions = [
            q
            for q in suggestion.get("unresolved_questions") or []
            if isinstance(q, str) and q.strip()
        ]
        for item in suggestion.get("fields") or []:
            field = item.get("field") if isinstance(item.get("field"), str) else "unknown"
            try:
                if field in {"schedule", "deadline"} and not time_basis_available:
                    raise ValueError("Missing time basis")
                validate_field_value(field, item.get("value"))
                NewWorkOrderSuggestedField.model_validate(item)
            except (ValidationError, ValueError):
                notes.append("llm:field-omitted:" + (field if field in FIELDS else "unknown"))
                if field in {"schedule", "deadline"} and not time_basis_available:
                    notes.append("llm:time-basis-missing")
                if field in FIELDS:
                    missing.append(field)
                    open_questions.append(f"请补充或核对{FIELD_LABELS[field]}。")
            else:
                # A scalar partial schedule is evidence, not a calendar interval.
                if field == "schedule" and not isinstance(item.get("value"), dict):
                    missing.append(field)
                    open_questions.append("请补充结束时间或时长，已识别的业务仍可建单。")
                    notes.append("llm:field-omitted:schedule")
                else:
                    valid.append(item)
        suggestion["fields"] = valid
        suggestion["missing_fields"] = list(dict.fromkeys(missing))
        suggestion["unresolved_questions"] = list(dict.fromkeys(open_questions))
    if data.get("assignment") == "matched" and not changes:
        data["changes"] = original_changes
        data["unresolved_questions"] = original_questions or []
        return []
    return notes


FIELD_LABELS = {
    "schedule": "时间安排",
    "address": "地址",
    "summary": "业务内容",
    "quantity": "数量",
    "specification": "规格",
    "deadline": "截止时间",
}


def validate_field_value(field, value, *, partial_schedule=False):
    if value is None:
        return
    if field in {"address", "summary", "specification"} and not isinstance(value, str):
        raise ValueError("Text field must be text")
    if field == "quantity" and (
        isinstance(value, bool) or not isinstance(value, (int, float, str))
    ):
        raise ValueError("Quantity must be a scalar")
    if (
        field == "schedule"
        and not partial_schedule
        and (not isinstance(value, dict) or value.get("kind") not in {"timed", "date_only"})
    ):
        raise ValueError("Incomplete schedule")
    if field == "deadline" and (
        not isinstance(value, dict) or value.get("kind") not in {"instant", "date_only"}
    ):
        raise ValueError("Invalid deadline")
