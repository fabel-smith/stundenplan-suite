"""The public v0.13 export: account isolation, course choices and honest coverage."""
import asyncio
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from stundenplan24_week.schulmanager_schedule import (
    SchulmanagerScheduleProvider, course_options, normalize_schedule, read_schedules,
    select_student,
)
from stundenplan24_week.model import compact_week_attributes

DAY = date(2026, 11, 2)
NOW = datetime.fromisoformat("2026-11-02T07:00:00+01:00")


def lesson(course="10", **changes):
    return {"id": "2026-11-02-slot1", "date": DAY.isoformat(), "period": "1",
            "start": "2026-11-02T08:00:00+01:00", "end": "2026-11-02T08:45:00+01:00",
            "subject": "Ph", "subject_full": "Physik", "course_id": course, "group": "Gruppe 1",
            "teachers": ["AB"], "rooms": ["EDV1"], "kind": "lesson", "status": "scheduled",
            "changes": [], "notes": [], "original": None, "source_type": "regularLesson", **changes}


def student(items=None, **changes):
    return {"config_entry_id": "account-a", "student_id": "child", "name": "Demo",
            "status": "ok", "fetched_at": NOW.isoformat(),
            "range": {"start": DAY.isoformat(), "end": "2026-11-15"},
            "periods": [{"period": "1", "start": "07:45", "end": "08:30"}],
            "days": [{"date": (DAY + timedelta(days=i)).isoformat(), "loaded": True,
                      "lessons": (items if items is not None else [lesson()]) if i == 0 else []}
                     for i in range(14)], **changes}


def result(s=None, config=None, monday=DAY, now=NOW):
    return normalize_schedule(s or student(), monday, now, config or {})


def test_structured_fields_and_actual_times_preserved():
    item = lesson(status="changed", changes=["room"], notes=["Material mitbringen"],
                  original={"rooms": ["204"]})
    data = result(student([item]))
    stored = data["lessons"][0]
    for key in ("date", "period", "start", "end", "subject", "subject_full", "teachers", "rooms",
                "kind", "status", "changes", "notes", "original", "source_type", "course_id", "group"):
        assert stored[key] == item[key]
    assert stored["source_id"] == item["id"]
    assert data["rows_table"][0]["start"] == "08:00"
    assert data["daily"]["today"]["routine_ready"]
    assert compact_week_attributes(data)["meta"]["source_interface"] == "get_schedule"


def test_same_child_id_in_different_accounts_and_ambiguity():
    a, b = student(), student(config_entry_id="account-b")
    assert select_student([a, b], "account-b", "child") is b
    for values in ([a], [a, b, b]):
        with pytest.raises(ValueError):
            select_student(values, "account-b", "child")


def test_exclusions_are_exposed_even_when_no_matching_lessons_are_loaded():
    config = {"excluded_course_ids": ["10", "99"]}
    attrs = compact_week_attributes(result(config=config))
    courses = attrs["meta"]["excluded_courses"]
    assert [course["id"] for course in courses] == ["10", "99"]
    assert "Physik" in courses[0]["label"]
    assert courses[1]["label"] == "Gespeicherter Kurs (Kurs 99)"
    assert not attrs["rows_table"]
    assert compact_week_attributes(result())["meta"]["excluded_courses"] == []
    missing = result(student(days=[], status="unavailable", fetched_at=None, range=None), config)
    assert [c["id"] for c in missing["meta"]["excluded_courses"]] == ["10", "99"]


def test_loaded_empty_is_no_school_but_missing_is_unknown():
    data = result(student([]))
    assert data["daily"]["today"]["school_day"] == "no"
    assert data["meta"]["coverage"] == "reported"
    missing = student(days=[])
    assert result(missing)["daily"]["today"]["school_day"] == "unknown"
    assert "week_not_fully_loaded" in result(missing)["meta"]["issues"]


@pytest.mark.parametrize("status", ["stale", "unavailable"])
def test_unfresh_data_never_confirms_school_routines(status):
    s = student(status=status)
    if status == "unavailable":
        s.update(fetched_at=None, range=None, days=[])
    data = result(s)
    today = data["daily"]["today"]
    assert not today["routine_ready"] and not today["source_fresh"]
    assert today["school_day"] == "unknown"
    assert data["meta"]["source_updated_at"] == s["fetched_at"]
    assert bool(data["rows_table"]) is (status == "stale")


@pytest.mark.parametrize("age,fresh", [(74, True), (75, False), (-2, False)])
def test_source_age_not_poll_time(age, fresh):
    s = student(fetched_at=(NOW - timedelta(minutes=age)).isoformat())
    data = result(s)
    assert data["daily"]["today"]["source_fresh"] is fresh
    assert data["meta"]["fetched_at"] == s["fetched_at"]


def test_view_week_does_not_change_today_and_out_of_range_not_empty_proof():
    data = result(monday=date(2026, 11, 16))
    assert data["rows_table"] == []
    assert data["meta"]["loaded_days"] == []
    assert data["daily"]["today"]["school_day"] == "yes"
    assert data["daily"]["today"]["routine_ready"]


def test_course_exclusion_not_subject_room_filter():
    s = student([lesson(), lesson("20", rooms=["EDV2"]), lesson("30", subject="M", period="2")])
    data = result(s, {"excluded_course_ids": ["10"]})
    assert [x["course_id"] for x in data["lessons"]] == ["20", "30"]
    assert "ambiguous_parallel_lessons" not in data["meta"]["issues"]
    assert result(s)["daily"]["today"]["routine_ready"] is False
    assert len(result(s)["lessons"]) == 3


def test_weekday_filter_keeps_tuesday_and_parallel_courses():
    s = student([])
    for offset in (0, 1, 7, 8):
        day = s["days"][offset]["date"]
        s["days"][offset]["lessons"] = [lesson(
            course, id=f"{day}-{period}-{course}", date=day, period=period,
            subject="Ku" if course == "10" else "Ev",
            start=f"{day}T11:30:00+01:00", end=f"{day}T12:15:00+01:00")
            for course in ("10", "20") for period in ("5", "6")]
    config = {"excluded_course_weekdays": {"10": ["mon"]}}
    data = result(s, config)
    art = [item for item in data["lessons"] if item["course_id"] == "10"]
    assert {(item["date"], item["period"]) for item in art} == {
        (s["days"][offset]["date"], period) for offset in (1, 8) for period in ("5", "6")}
    assert len([item for item in data["lessons"] if item["course_id"] == "20"]) == 8
    assert len(s["days"][0]["lessons"]) == 4  # Source remains untouched.
    attrs = compact_week_attributes(data)
    assert attrs["meta"]["excluded_courses"][0]["weekdays"] == ["mon"]
    assert "nur Montag" in attrs["meta"]["excluded_courses"][0]["label"]
    assert data["daily"]["today"]["routine_ready"]


def test_weekday_rules_compose_with_global_rules_and_keep_missing_course_metadata():
    s = student([lesson(), lesson("20")])
    config = {"excluded_course_ids": ["20"],
              "excluded_course_weekdays": {"10": ["tue"], "99": ["fri", "mon"]}}
    data = result(s, config)
    assert [item["course_id"] for item in data["lessons"]] == ["10"]
    courses = {item["id"]: item for item in data["meta"]["excluded_courses"]}
    assert "weekdays" not in courses["20"]
    assert courses["99"]["weekdays"] == ["mon", "fri"]
    assert "Gespeicherter Kurs" in courses["99"]["label"]
    assert "nur Montag, Freitag" in courses["99"]["label"]
    config["excluded_course_ids"].append("10")
    assert result(s, config)["lessons"] == []


@pytest.mark.parametrize("days,warning", [(["mon"], True), (["tue"], False)])
def test_weekday_filter_preserves_unknown_special_lessons(days, warning):
    s = student([lesson(None, source_type="specialLesson")])
    data = result(s, {"excluded_course_weekdays": {"10": days}})
    assert len(data["lessons"]) == 1
    assert ("special_lesson_without_course" in data["meta"]["issues"]) is warning


@pytest.mark.parametrize("rules", [[], {"10": []}, {"10": ["bad"]}, {"10": "mon"}])
def test_invalid_weekday_rules_fail_instead_of_hiding_all_days(rules):
    with pytest.raises(ValueError):
        result(config={"excluded_course_weekdays": rules})


def test_weekday_filter_uses_lesson_date_not_selected_week_or_current_day():
    s = student([lesson()])
    config = {"excluded_course_weekdays": {"10": ["mon"]}}
    data = result(s, config, monday=DAY + timedelta(days=7), now=NOW + timedelta(days=1))
    assert not data["lessons"]


def test_weekend_weekday_rules():
    s = student([])
    day = s["days"][5]["date"]
    s["days"][5]["lessons"] = [lesson(date=day, id=f"{day}-1",
        start=f"{day}T08:00:00+01:00", end=f"{day}T08:45:00+01:00")]
    assert len(result(s, {"excluded_course_weekdays": {"10": ["mon"]}})["lessons"]) == 1
    assert not result(s, {"excluded_course_weekdays": {"10": ["sat"]}})["lessons"]


def test_special_without_course_is_never_guessed_away():
    special = lesson(None, status="changed", source_type="specialLesson", group="Gruppe 1")
    cancelled = lesson(status="cancelled", changes=["cancellation"])
    data = result(student([cancelled, special]), {"excluded_course_ids": ["10"]})
    assert len(data["lessons"]) == 1
    assert data["lessons"][0]["source_type"] == "specialLesson"
    assert "special_lesson_without_course" in data["meta"]["issues"]
    both = result(student([cancelled, special]))
    assert len(both["lessons"]) == 2
    assert "Entfällt" in both["rows_table"][0]["Mo"]


def test_course_options_deduplicate_keep_missing_and_never_use_rooms_as_keys():
    s = student([lesson(), lesson(rooms=["EDV2"]), lesson(None)])
    choices = course_options(s, ["99"])
    assert [c["value"] for c in choices] == ["10", "99"]
    assert "EDV1" in choices[0]["label"] and "EDV2" in choices[0]["label"]
    assert "Gespeicherter Kurs" in choices[1]["label"]


@pytest.mark.parametrize("change", [
    {"date": "2026-11-03"}, {"start": "2026-11-02T08:00:00"},
    {"end": "2026-11-02T07:00:00+01:00"}, {"kind": "new_kind"}, {"teachers": "AB"},
])
def test_invalid_lessons_do_not_silently_prove_completeness(change):
    with pytest.raises((ValueError, TypeError)):
        result(student([lesson(**change)]))


def test_invalid_range_and_duplicate_days():
    for s in (student(range={"start": "2026-11-10", "end": "2026-11-01"}),
              student(days=[student()["days"][0]] * 2)):
        with pytest.raises(ValueError):
            result(s)


def test_breaks_preserved_but_actual_lesson_times_take_precedence():
    second = lesson("20", period="2", start="2026-11-02T09:00:00+01:00",
                    end="2026-11-02T09:45:00+01:00")
    s = student([lesson(), second], periods=[
        {"period": "1", "start": "08:00", "end": "08:45"},
        {"period": "2", "start": "09:00", "end": "09:45"}])
    assert any(row.get("break") for row in result(s)["rows_table"])
    second["start"] = "2026-11-02T08:50:00+01:00"
    assert not any(row.get("break") for row in result(s)["rows_table"])


def test_weekend_empty_and_unloaded_day():
    s = student()
    saturday = NOW + timedelta(days=5)
    s["fetched_at"] = saturday.isoformat()
    assert result(s, now=saturday)["daily"]["today"]["school_day"] == "no"
    s["days"][5]["loaded"] = False
    assert result(s, now=saturday)["daily"]["today"]["school_day"] == "unknown"


def test_provider_calls_only_public_cached_service_and_filters_events():
    call = AsyncMock(return_value={"schema_version": 1, "source": "schulmanager", "students": [student()]})
    hass = SimpleNamespace(services=SimpleNamespace(has_service=lambda *a: True, async_call=call))
    config = {"schedule_entry_id": "account-a", "schedule_student_id": "child"}
    provider = SchulmanagerScheduleProvider(hass, config)
    asyncio.run(provider.fetch(DAY, NOW))
    call.assert_awaited_once_with("schulmanager", "get_schedule",
        {"config_entry_id": "account-a", "student_id": "child"}, blocking=True, return_response=True)
    assert provider.matches_event(SimpleNamespace(data={"config_entry_id": "account-a", "student_ids": ["child"]}))
    assert not provider.matches_event(SimpleNamespace(data={"config_entry_id": "account-b", "student_ids": ["child"]}))
    assert not provider.matches_event(SimpleNamespace(data={"config_entry_id": "account-a", "student_ids": ["other"]}))


def test_missing_service_and_unknown_schema_fail_not_legacy_fallback():
    call = AsyncMock(return_value={"schema_version": 2, "source": "schulmanager", "students": []})
    for available in (False, True):
        hass = SimpleNamespace(services=SimpleNamespace(has_service=lambda *a: available, async_call=call))
        with pytest.raises(ValueError):
            asyncio.run(read_schedules(hass))
