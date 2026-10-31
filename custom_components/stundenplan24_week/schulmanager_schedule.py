"""Public Schulmanager get_schedule contract; no upstream internals or requests."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from .model import Lesson, payload
from .schulmanager import add_missing_plan_breaks

DOMAIN = "schulmanager"
EVENT = "schulmanager_schedule_updated"
MAX_AGE = timedelta(minutes=75)
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
WEEKDAY_LABELS = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")


def course_weekdays(config):
    """Validate saved rules rather than silently widening an exclusion."""
    rules = config.get("excluded_course_weekdays", {})
    if not isinstance(rules, dict):
        raise ValueError("Invalid weekday course filters")
    for course, days in rules.items():
        if (not isinstance(course, str) or not course or not isinstance(days, list)
                or not days or any(day not in WEEKDAYS for day in days)):
            raise ValueError("Invalid weekday course filter")
    return rules


async def read_schedules(hass, **filters):
    if not hass.services.has_service(DOMAIN, "get_schedule"):
        raise ValueError("Schulmanager get_schedule ist nicht verfügbar")
    response = await hass.services.async_call(
        DOMAIN, "get_schedule", filters, blocking=True, return_response=True)
    if (not isinstance(response, dict) or response.get("schema_version") != 1
            or response.get("source") != DOMAIN
            or not isinstance(response.get("students"), list)):
        raise ValueError("Unbekanntes Schulmanager-Stundenplanformat")
    students = response["students"]
    if any(not isinstance(s, dict) or not s.get("config_entry_id")
           or not s.get("student_id") for s in students):
        raise ValueError("Ungültige Kind-Zuordnung im Stundenplan")
    return students


def select_student(students, entry_id, student_id):
    matches = [s for s in students if s["config_entry_id"] == entry_id
               and s["student_id"] == student_id]
    if len(matches) != 1:
        raise ValueError("Das ausgewählte Kind ist nicht eindeutig verfügbar")
    return matches[0]


def course_options(student, excluded=()):
    """Keep saved exclusions selectable even when their course is out of range."""
    labels = {str(value): set() for value in excluded}
    for day in student.get("days") or []:
        for lesson in day.get("lessons") or []:
            course = lesson.get("course_id")
            if course is None:
                continue
            parts = [lesson.get("subject_full") or lesson.get("subject"),
                     lesson.get("group"), ", ".join(lesson.get("teachers") or []),
                     ", ".join(lesson.get("rooms") or [])]
            labels.setdefault(str(course), set()).add(" / ".join(p for p in parts if p))
    return [{"value": key, "label": f"{' | '.join(sorted(values)) or 'Gespeicherter Kurs'} (Kurs {key})"}
            for key, values in sorted(labels.items())]


def _strings(value):
    if not isinstance(value, list) or any(not isinstance(x, str) for x in value):
        raise ValueError("Ungültige Liste in einer Unterrichtsstunde")
    return list(value)


def _time(value, day):
    if value is None:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.date().isoformat() != day:
        raise ValueError("Ungültiges Unterrichtsdatum oder fehlende Zeitzone")
    return parsed.isoformat()


def normalize_schedule(student, monday, now, config):
    status = student.get("status")
    if status not in ("ok", "stale", "unavailable"):
        raise ValueError("Unbekannter Schulmanager-Status")
    stamp = student.get("fetched_at")
    fresh, deadline = False, None
    if stamp:
        fetched = datetime.fromisoformat(stamp)
        if fetched.tzinfo is None:
            raise ValueError("Fehlende Zeitzone des Abrufzeitpunkts")
        deadline = (fetched + MAX_AGE).isoformat()
        fresh = status == "ok" and -60 <= (now - fetched).total_seconds() < MAX_AGE.total_seconds()
    days = student.get("days")
    if not isinstance(days, list):
        raise ValueError("Ungültige Tagesliste")
    source_range = student.get("range")
    if status != "unavailable":
        if not isinstance(source_range, dict) or not stamp:
            raise ValueError("Fehlender Zeitraum des Stundenplans")
        first = date.fromisoformat(source_range["start"])
        last = date.fromisoformat(source_range["end"])
        if first > last:
            raise ValueError("Ungültiger Zeitraum des Stundenplans")
    else:
        first = last = None
        days = []
    lessons, loaded, empty, seen = [], set(), set(), set()
    excluded = {str(value) for value in config.get("excluded_course_ids", [])}
    weekday_rules = course_weekdays(config)
    issues = []
    ambiguous = set()
    if not fresh:
        issues.append("source_unavailable" if status == "unavailable" else "source_stale")
    for day in days:
        day_id = day["date"]
        parsed_day = date.fromisoformat(day_id)
        excluded_today = excluded | {course for course, weekdays in weekday_rules.items()
                                     if WEEKDAYS[parsed_day.weekday()] in weekdays}
        if day_id in seen or not first <= parsed_day <= last:
            raise ValueError("Doppelter Tag oder Tag außerhalb des Quellzeitraums")
        seen.add(day_id)
        if day.get("loaded") is not True:
            continue
        entries = day.get("lessons")
        if not isinstance(entries, list):
            raise ValueError("Ungültige Stundenliste")
        loaded.add(day_id)
        if not entries:
            empty.add(day_id)
        slots = {}
        for item in entries:
            if item.get("date") != day_id or not item.get("id"):
                raise ValueError("Unterricht ohne eindeutiges Datum oder ID")
            course = item.get("course_id")
            if course is not None and str(course) in excluded_today:
                continue
            # Never infer membership of a special lesson from subject/room/group.
            if excluded_today and course is None and item.get("source_type") == "specialLesson":
                issues.append("special_lesson_without_course")
                ambiguous.add(day_id)
            start, end = _time(item.get("start"), day_id), _time(item.get("end"), day_id)
            if start and end and datetime.fromisoformat(end) <= datetime.fromisoformat(start):
                raise ValueError("Unterricht endet vor dem Beginn")
            lesson = Lesson(
                date=day_id, start=start, end=end, period=str(item.get("period") or ""),
                subject=str(item.get("subject") or ""), subject_full=str(item.get("subject_full") or ""),
                teachers=_strings(item.get("teachers", [])), rooms=_strings(item.get("rooms", [])),
                kind=item.get("kind", "unknown"), status=item.get("status", "unknown"),
                changes=_strings(item.get("changes", [])), notes=_strings(item.get("notes", [])),
                original=item.get("original"), source_type=str(item.get("source_type") or ""),
                source_id=str(item["id"]), confidence="corroborated" if fresh else "reported",
                course_id=str(course) if course is not None else None, group=item.get("group"),
            )
            if lesson.kind not in ("lesson", "event", "break", "unknown") or lesson.status not in (
                    "scheduled", "changed", "cancelled", "unknown"):
                raise ValueError("Unbekannte Unterrichtsart")
            lessons.append(lesson)
            if lesson.kind != "break" and lesson.status != "cancelled":
                slots.setdefault(lesson.period or start, []).append(lesson)
        if any(len(items) > 1 for items in slots.values()):
            ambiguous.add(day_id)
            issues.append("ambiguous_parallel_lessons")
    weekdays = {(monday + timedelta(days=i)).isoformat() for i in range(5)}
    if not weekdays <= loaded:
        issues.append("week_not_fully_loaded")
    # Preserve pause rows from the school's period table, never over actual lessons.
    plan = [{"Stunde": f"{p['period']}. {p['start']} - {p['end']}"}
            for p in student.get("periods", []) if p.get("start") and p.get("end")]
    with_breaks = list(lessons)
    add_missing_plan_breaks(with_breaks, plan, now.tzinfo)
    for pause in with_breaks[len(lessons):]:
        if not any(item.date == pause.date and item.start and item.end
                   and item.kind != "break"
                   and datetime.fromisoformat(item.start) < datetime.fromisoformat(pause.end)
                   and datetime.fromisoformat(item.end) > datetime.fromisoformat(pause.start)
                   for item in lessons):
            lessons.append(pause)
    result = payload(
        lessons, monday, now.date(), provider=DOMAIN,
        target=config.get("target", "Stundenplan"), fetched_at=stamp,
        verified_days=(loaded - ambiguous) if fresh else set(), issues=issues,
        show_room=config.get("show_room", True), show_teacher=config.get("show_teacher", False))
    # Internal cache only: adjacent-week data must not inflate recorder attributes.
    result["view_loaded_days"] = sorted(loaded)
    excluded_metadata = []
    for option in course_options(student, excluded | set(weekday_rules)):
        course = option["value"]
        if course in excluded:
            excluded_metadata.append({"id": course, "label": option["label"]})
        elif course in weekday_rules:
            selected = [day for day in WEEKDAYS if day in weekday_rules[course]]
            names = ", ".join(WEEKDAY_LABELS[WEEKDAYS.index(day)] for day in selected)
            excluded_metadata.append({"id": course, "label": f"{option['label']} - nur {names}",
                                      "weekdays": selected})
    result["meta"].update({
        "source_updated_at": stamp, "source_status": status, "source_interface": "get_schedule",
        "coverage": "reported" if fresh and weekdays <= loaded else "stale" if not fresh else "partial",
        "loaded_days": sorted(loaded & weekdays),
        "excluded_courses": excluded_metadata,
    })
    for summary in result["daily"].values():
        day_id = summary["date"]
        summary.update(source_updated_at=stamp, source_valid_until=deadline,
                       source_fresh=fresh, loaded=day_id in loaded, source_status=status)
        if fresh and day_id in empty:
            summary["school_day"] = "no"
        if not fresh or day_id not in loaded:
            summary["school_day"] = "unknown"
            summary["routine_ready"] = False
    return result


class SchulmanagerScheduleProvider:
    name = DOMAIN
    entity_ids = ()

    def __init__(self, hass, config):
        self.hass, self.config = hass, config

    def matches_event(self, event):
        return (event.data.get("config_entry_id") == self.config["schedule_entry_id"]
                and self.config["schedule_student_id"] in event.data.get("student_ids", []))

    async def fetch(self, monday, now):
        entry_id, student_id = self.config["schedule_entry_id"], self.config["schedule_student_id"]
        students = await read_schedules(self.hass, config_entry_id=entry_id, student_id=student_id)
        student = select_student(students, entry_id, student_id)
        return normalize_schedule(student, monday, now, self.config)
