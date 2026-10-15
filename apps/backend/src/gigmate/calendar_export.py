"""Read-only RFC 5545 export. No external calendar connection or writes."""

from datetime import UTC, datetime

from gigmate.errors import BusinessError


def escape(value):
    return (
        "".join(c for c in value if c in "\r\n\t" or ord(c) >= 32)
        .replace("\\", "\\\\")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", "\\n")
        .replace(";", "\\;")
        .replace(",", "\\,")
    )


def fold(line):
    """Fold at 75 UTF-8 octets without splitting a multibyte character."""
    parts, current = [], ""
    for char in line:
        if len((current + char).encode("utf-8")) > 75:
            parts.append(current)
            current = " "
        current += char
    parts.append(current)
    return "\r\n".join(parts)


def stamp(value):
    return datetime.fromisoformat(value).astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def export_event(event, order):
    if (
        event["work_order_version"] != order["version"]
        or event["schedule"] != order["fields"]["schedule"]["value"]
    ):
        raise BusinessError(409, "VERSION_CONFLICT", "Refresh the current appointment")
    if (
        event["tentative"]
        or event["schedule"]["kind"] != "timed"
        or order["status"] not in {"confirmed", "in_progress", "waiting_customer"}
        or order["fields"]["schedule"]["status"] != "confirmed"
    ):
        raise BusinessError(
            409, "CALENDAR_NOT_EXPORTABLE", "Only current confirmed appointments export"
        )
    schedule = event["schedule"]
    address = order["fields"]["address"]
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//GigMate//Appointments//ZH",
        "CALSCALE:GREGORIAN",
        "BEGIN:VEVENT",
        f"UID:{event['id']}@gigmate.local",
        f"SEQUENCE:{order['version']}",
        "DTSTAMP:" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
        "LAST-MODIFIED:" + stamp(order["updated_at"]),
        "DTSTART:" + stamp(schedule["start_at"]),
        "DTEND:" + stamp(schedule["end_at"]),
        "SUMMARY:" + escape(order["summary"]),
        "DESCRIPTION:" + escape("来自跟單 GigMate；原时区 " + schedule["timezone"]),
        "STATUS:CONFIRMED",
        "TRANSP:OPAQUE",
    ]
    # Do not turn a proposed location into a confirmed calendar location.
    if address["status"] == "confirmed" and isinstance(address["value"], str):
        lines.append("LOCATION:" + escape(address["value"]))
    lines.extend(["END:VEVENT", "END:VCALENDAR"])
    return ("\r\n".join(fold(line) for line in lines) + "\r\n").encode("utf-8")
