"""Adapter for the public calendar service and Schulmanager entity attributes.

No credentials, private coordinator access, or second Schulmanager API session.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
import re
from typing import Any

from .model import Lesson, payload

# The upstream integration polls hourly. Allow one interval plus 15 minutes
# scheduling grace; rereading the HA entity must never extend this deadline.
SOURCE_MAX_AGE = timedelta(minutes=75)
MIN_INFERRED_BREAK_MINUTES = 10

TYPE_MAP = {
    "regularLesson": ("lesson", "scheduled", []),
    "cancelledLesson": ("lesson", "cancelled", ["cancellation"]),
    "substitution": ("lesson", "changed", ["substitution"]),
    "teacherChange": ("lesson", "changed", ["teacher"]),
    "roomChange": ("lesson", "changed", ["room"]),
    "specialLesson": ("lesson", "changed", ["special"]),
    "irregularLesson": ("lesson", "changed", ["irregular"]),
    "exam": ("lesson", "changed", ["exam"]),
    "event": ("event", "scheduled", []),
}


def parse_time(value: Any, zone) -> datetime | None:
    if not isinstance(value, str) or "T" not in value:
        return None  # all-day events never become timed lessons
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone(zone) if dt.tzinfo else None
    except ValueError:
        return None


def period_times(plan: list[dict]) -> dict[tuple[str, str], str]:
    out = {}
    for row in plan:
        label = str(row.get("Stunde", ""))
        m = re.match(r"^(.*?)\.\s+(\d{2}:\d{2})(?::\d{2})?\s*[-–]\s*(\d{2}:\d{2})(?::\d{2})?$", label)
        if m:
            out[(m[2], m[3])] = m[1]
    return out


def plan_break_slots(plan: list[dict]) -> list[tuple[str, str, str]]:
    """Return explicit and safely inferred breaks from the period table."""
    explicit = []
    lessons = []
    for row in plan:
        label = str(row.get("Stunde", ""))
        match = re.match(r"^(.*?)\.\s+(\d{2}:\d{2})(?::\d{2})?\s*[-–]\s*(\d{2}:\d{2})(?::\d{2})?$", label)
        if not match:
            continue
        slot = (match[1], match[2], match[3])
        if "pa" in match[1].lower() or "pause" in match[1].lower():
            explicit.append(slot)
        else:
            lessons.append(slot)

    def minutes(value: str) -> int:
        hour, minute = (int(part) for part in value.split(":"))
        return hour * 60 + minute

    inferred = []
    ordered_slots = sorted(set(lessons), key=lambda item: (minutes(item[1]), minutes(item[2])))
    for previous, following in zip(ordered_slots, ordered_slots[1:]):
        gap_start, gap_end = previous[2], following[1]
        if minutes(gap_end) - minutes(gap_start) < MIN_INFERRED_BREAK_MINUTES:
            continue
        # An explicit break within the same gap is more authoritative.
        if any(minutes(start) >= minutes(gap_start) and minutes(end) <= minutes(gap_end)
               for _, start, end in explicit):
            continue
        inferred.append(("Pause", gap_start, gap_end))
    return sorted(explicit + inferred, key=lambda item: (minutes(item[1]), minutes(item[2])))


def add_missing_plan_breaks(lessons: list[Lesson], plan: list[dict], zone) -> None:
    """Add omitted calendar breaks only when lessons surround the slot."""
    for day in sorted({item.date for item in lessons}):
        day_lessons = [item for item in lessons if item.date == day and item.kind != "break"
                       and item.start and item.end]
        if not day_lessons:
            continue
        starts = [datetime.fromisoformat(item.start) for item in day_lessons]
        ends = [datetime.fromisoformat(item.end) for item in day_lessons]
        first_start, last_end = min(starts), max(ends)
        for period, start_text, end_text in plan_break_slots(plan):
            start = datetime.fromisoformat(f"{day}T{start_text}:00").replace(tzinfo=zone)
            end = datetime.fromisoformat(f"{day}T{end_text}:00").replace(tzinfo=zone)
            if not (first_start < start < end < last_end):
                continue
            if any(item.date == day and item.kind == "break" and
                   item.start and item.end and
                   datetime.fromisoformat(item.start) == start and
                   datetime.fromisoformat(item.end) == end for item in lessons):
                continue
            lessons.append(Lesson(day, start.isoformat(), end.isoformat(), period=period,
                                  kind="break", status="scheduled", source_type="planBreak",
                                  confidence="inferred"))


def normalize(events: list[dict], raw_days: dict[str, list[dict]], plan: list[dict],
              zone, source_id: str = "") -> tuple[list[Lesson], set[str], list[str]]:
    slots = period_times(plan)
    lessons, issues = [], []
    matched: dict[str, set[int]] = {}
    bad_days: set[str] = set()
    seen: set[str] = set()
    for event in events:
        start, end = parse_time(event.get("start"), zone), parse_time(event.get("end"), zone)
        if start is None or end is None or end <= start or start.date() != end.date():
            issues.append("invalid_or_all_day_event")
            for dt in (start, end):
                if dt:
                    bad_days.add(dt.date().isoformat())
            continue
        day = start.date().isoformat()
        fields = {}
        for line in str(event.get("description") or "").splitlines():
            key, sep, value = line.partition(":")
            if sep:
                fields[key.strip()] = value.strip()
        title = str(event.get("summary") or "").strip()
        source_type = fields.get("Typ", "regularLesson")
        if title.startswith(("❌", "X ")):
            source_type = "cancelledLesson"
        if title.startswith("🔁") and "Typ" not in fields:
            source_type = "unknown"  # the icon cannot distinguish several change types
        title = re.sub(r"^(?:❌|🔁|🚪|📝|X )\s*", "", title)
        room = fields.get("Raum", str(event.get("location") or ""))
        if room and title.endswith(" – " + room):
            title = title[:-(len(room) + 3)]
        period = slots.get((start.strftime("%H:%M"), end.strftime("%H:%M")), "")
        raw_list = raw_days.get(day, [])
        candidates = [(i, x) for i, x in enumerate(raw_list) if str(x.get("hour", "")) == period and period]
        # Replacement wins over cancellation only when exactly one active item exists.
        active = [(i, x) for i, x in candidates if x.get("type") != "cancelledLesson"]
        chosen = active if active else candidates
        if len(chosen) > 1:
            issues.append("ambiguous_parallel_lessons")
        raw = chosen[0][1] if len(chosen) == 1 else None
        consistent = bool(raw and raw.get("type", "regularLesson") == source_type and
                          (not raw.get("subject") or raw.get("subject") == title) and
                          (not raw.get("room") or raw.get("room") == room) and
                          (not raw.get("teacher") or raw.get("teacher") == fields.get("Lehrer", "")))
        if raw and not consistent:
            bad_days.add(day)
            issues.append("calendar_raw_disagreement")
        kind, status, changes = TYPE_MAP.get(source_type, ("unknown", "unknown", []))
        if period and ("pa" in period.lower() or "pause" in period.lower()):
            kind = "break"
        if consistent:
            matched.setdefault(day, set()).update(i for i, _ in candidates)
        else:
            bad_days.add(day)
        teachers = fields.get("Lehrer", "")
        lesson = Lesson(day, start.isoformat(), end.isoformat(), period=period,
                        subject=(raw.get("subject", "") if consistent else title if title != "Unterricht" else ""),
                        subject_full=raw.get("subject_full", "") if consistent else "",
                        teachers=[x.strip() for x in teachers.split(",") if x.strip()],
                        rooms=[room] if room else [], kind=kind, status=status, changes=list(changes),
                        notes=[fields["Hinweis"]] if fields.get("Hinweis") else [],
                        original={"text": fields["Ursprünglich"]} if fields.get("Ursprünglich") else None,
                        source_type=source_type, source_id=source_id,
                        confidence="corroborated" if consistent else "reported")
        identity = lesson.to_dict()["id"]
        if identity not in seen:
            lessons.append(lesson)
            seen.add(identity)
    add_missing_plan_breaks(lessons, plan, zone)
    verified = {d for d, raw in raw_days.items() if raw and d not in bad_days and
                len(matched.get(d, set())) == len(raw)}
    if issues:
        # An invalid event without a usable date prevents a complete-day claim.
        if "invalid_or_all_day_event" in issues:
            verified.clear()
    return lessons, verified, issues


class SchulmanagerProvider:
    name = "schulmanager"

    def __init__(self, hass, config: dict[str, Any]):
        self.hass, self.config = hass, config

    @property
    def entity_ids(self):
        return [self.config[k] for k in ("calendar_entity", "today_entity", "tomorrow_entity", "week_entity", "changes_entity") if self.config.get(k)]

    async def fetch(self, monday: date, now: datetime) -> dict[str, Any]:
        calendar = self.config["calendar_entity"]
        state = self.hass.states.get(calendar)
        if state is None or state.state in ("unknown", "unavailable"):
            raise ValueError("Stundenplankalender ist nicht verfügbar")
        # Always include today/tomorrow independently of the displayed week.
        first = min(monday, now.date())
        last = max(monday + timedelta(days=7), now.date() + timedelta(days=2))
        response = await self.hass.services.async_call("calendar", "get_events", {
            "entity_id": calendar,
            "start_date_time": datetime.combine(first, datetime.min.time(), now.tzinfo).isoformat(),
            "end_date_time": datetime.combine(last, datetime.min.time(), now.tzinfo).isoformat(),
        }, blocking=True, return_response=True)
        if not isinstance(response, dict) or not isinstance(response.get(calendar, {}).get("events"), list):
            raise ValueError("Ungültige Kalenderantwort")
        raw_days = {}
        source_times = {}
        source_deadlines = {}
        fresh_days = set()
        for key, day in (("today_entity", now.date()), ("tomorrow_entity", now.date() + timedelta(days=1))):
            entity = self.hass.states.get(self.config.get(key, ""))
            if not entity or entity.state in ("unknown", "unavailable"):
                continue
            raw = entity.attributes.get("raw") or {}
            if not isinstance(raw, dict):
                continue
            values = raw.get("lessons")
            if isinstance(values, list) and all(isinstance(x, dict) and x.get("date") == day.isoformat() for x in values):
                raw_days[day.isoformat()] = values
                # Schulmanager 0.9.1 stamps tomorrow with now + one day.
                # last_updated alone is not proof of a successful upstream fetch.
                try:
                    stamp = datetime.fromisoformat(raw.get("date", ""))
                    if stamp.tzinfo is None:
                        stamp = stamp.replace(tzinfo=now.tzinfo)
                    stamp -= timedelta(days=(day - now.date()).days)
                    source_times[day.isoformat()] = stamp.isoformat()
                    deadline = datetime.fromtimestamp(stamp.timestamp() + SOURCE_MAX_AGE.total_seconds(), now.tzinfo)
                    source_deadlines[day.isoformat()] = deadline.isoformat()
                    age = now.timestamp() - stamp.timestamp()
                    if -60 <= age < SOURCE_MAX_AGE.total_seconds():
                        fresh_days.add(day.isoformat())
                except (ValueError, TypeError):
                    pass
        week = self.hass.states.get(self.config.get("week_entity", ""))
        plan = week.attributes.get("plan", []) if week and week.state not in ("unknown", "unavailable") else []
        lessons, verified, issues = normalize(response[calendar]["events"], raw_days,
                                              plan if isinstance(plan, list) else [], now.tzinfo, calendar)
        verified &= fresh_days
        if any(d not in fresh_days for d in raw_days):
            issues.append("source_freshness_unverified")
        changes_state = self.hass.states.get(self.config.get("changes_entity", ""))
        changes = (changes_state.attributes.get("changes") or {}) if changes_state and changes_state.state not in ("unavailable", "unknown") else {}
        if isinstance(changes, dict):
            for entries in (changes.get("today", []), changes.get("tomorrow", [])):
                for change in entries if isinstance(entries, list) else []:
                    if not isinstance(change, dict):
                        continue
                    for lesson in lessons:
                        if lesson.date == change.get("date") and lesson.period == str(change.get("hour", "")):
                            original = {key: change.get("original_" + key) for key in ("subject", "teacher", "room") if change.get("original_" + key)}
                            if original:
                                lesson.original = original
                            for key in ("reason", "note"):
                                if change.get(key) and str(change[key]) not in lesson.notes:
                                    lesson.notes.append(str(change[key]))
        result = payload(lessons, monday, now.date(), provider=self.name,
                       target=self.config.get("target", "Stundenplan"), fetched_at=now.isoformat(),
                       verified_days=verified, issues=issues,
                       show_room=self.config.get("show_room", True),
                       show_teacher=self.config.get("show_teacher", False))
        for summary in result["daily"].values():
            summary["source_updated_at"] = source_times.get(summary["date"])
            summary["source_valid_until"] = source_deadlines.get(summary["date"])
            summary["source_fresh"] = summary["date"] in fresh_days
        return result
