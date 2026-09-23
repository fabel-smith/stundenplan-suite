import asyncio
import json
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from stundenplan24_week.model import Lesson, card_rows, compact_week_attributes, day_summary, payload
from stundenplan24_week.schulmanager import SchulmanagerProvider, normalize, period_times

ZONE = timezone(timedelta(hours=2))
DAY = date(2026, 9, 17)
NOW = datetime(2026, 9, 17, 6, 30, tzinfo=ZONE)
PLAN = [
    {"Stunde": "1. 07:45:00 - 08:30:00"},
    {"Stunde": "2. 08:35:00 - 09:20:00"},
    {"Stunde": "*1.gr.Pa.. 09:20:00 - 09:40:00"},
]


def event(start="07:45", end="08:30", summary="D – R1", desc="Lehrer: T1\nRaum: R1", day=DAY):
    return {"start": f"{day}T{start}:00+02:00", "end": f"{day}T{end}:00+02:00",
            "summary": summary, "description": desc}


def raw(hour="1", subject="D", kind="regularLesson", day=DAY):
    return {"hour": hour, "subject": subject, "subject_full": "Deutsch" if subject == "D" else subject,
            "teacher": "", "room": "", "type": kind, "date": str(day)}


def normal(events, raws, plan=PLAN):
    return normalize(events, {str(DAY): raws}, plan, ZONE)


def test_live_shape_lesson_and_readiness():
    lessons, verified, issues = normal([event()], [raw()])
    assert verified == {str(DAY)} and issues == []
    item = lessons[0]
    assert (item.subject, item.subject_full, item.rooms, item.teachers) == ("D", "Deutsch", ["R1"], ["T1"])
    summary = day_summary(lessons, DAY, verified=True)
    assert summary["routine_ready"] and summary["first_start"].endswith("07:45:00+02:00")


def test_cancelled_first_hour_moves_start():
    items, verified, _ = normal([
        event(summary="❌ D – R1", desc="Raum: R1\nTyp: cancelledLesson"),
        event("08:35", "09:20", "M", "")],
        [raw(kind="cancelledLesson"), raw("2", "M")])
    result = day_summary(items, DAY, verified=str(DAY) in verified)
    assert result["first_start"].endswith("08:35:00+02:00")
    assert result["first_lesson_cancelled"] is True
    assert result["cancelled_count"] == 1
    assert result["subjects"] == ["M"]
    assert result["routine_ready"]


def test_missing_first_hour_does_not_claim_cancellation():
    items, _, _ = normal([event("08:35", "09:20", "M", "")], [raw("2", "M")])
    assert day_summary(items, DAY)["first_lesson_cancelled"] is False


def test_pause_not_counted_as_subject_or_attendance():
    items, verified, _ = normal([event(), event("09:20", "09:40", "Unterricht", "Typ: event")],
                               [raw(), raw("*1.gr.Pa.", "", "event")])
    assert items[1].kind == "break"
    result = day_summary(items, DAY, verified=bool(verified))
    assert result["last_end"].endswith("08:30:00+02:00")
    assert result["subjects"] == ["Deutsch"]


def test_missing_calendar_pause_is_added_from_period_table_for_card():
    plan = [
        {"Stunde": "1. 07:45:00 - 08:30:00"},
        {"Stunde": "2. 08:35:00 - 09:20:00"},
        {"Stunde": "*1.gr.Pa.. 09:20:00 - 09:40:00"},
        {"Stunde": "3. 09:40:00 - 10:25:00"},
    ]
    items, verified, issues = normal([
        event(),
        event("08:35", "09:20", "M", ""),
        event("09:40", "10:25", "E", ""),
    ], [raw(), raw("2", "M"), raw("3", "E")], plan)
    breaks = [item for item in items if item.kind == "break"]
    assert len(breaks) == 1 and breaks[0].start.endswith("09:20:00+02:00")
    assert verified == {str(DAY)} and issues == []
    rows, table = card_rows(items, date(2026, 9, 14))
    pause = next(row for row in rows if row.get("break"))
    assert pause == {"break": True, "time": "09:20–09:40", "start": "09:20",
                     "end": "09:40", "label": "Pause"}
    assert next(row for row in table if row.get("break")) == pause


def test_long_period_gaps_are_inferred_as_breaks_but_short_changes_are_not():
    plan = [
        {"Stunde": "1. 07:45:00 - 08:30:00"},
        {"Stunde": "2. 08:35:00 - 09:20:00"},
        {"Stunde": "3. 09:40:00 - 10:25:00"},
        {"Stunde": "4. 10:30:00 - 11:15:00"},
        {"Stunde": "5. 11:40:00 - 12:25:00"},
    ]
    events = [
        event(),
        event("08:35", "09:20", "M", ""),
        event("09:40", "10:25", "E", ""),
        event("10:30", "11:15", "M", ""),
        event("11:40", "12:25", "E", ""),
    ]
    raws = [raw(), raw("2", "M"), raw("3", "E"), raw("4", "M"), raw("5", "E")]
    items, _, _ = normal(events, raws, plan)
    breaks = [(item.start[11:16], item.end[11:16]) for item in items if item.kind == "break"]
    assert breaks == [("09:20", "09:40"), ("11:15", "11:40")]


def test_explicit_break_wins_over_inferred_gap():
    plan = [
        {"Stunde": "2. 08:35:00 - 09:20:00"},
        {"Stunde": "große Pause. 09:20:00 - 09:40:00"},
        {"Stunde": "3. 09:40:00 - 10:25:00"},
    ]
    items, _, _ = normal([
        event("08:35", "09:20", "M", ""),
        event("09:40", "10:25", "E", ""),
    ], [raw("2", "M"), raw("3", "E")], plan)
    breaks = [item for item in items if item.kind == "break"]
    assert len(breaks) == 1 and breaks[0].period == "große Pause"


def test_existing_calendar_pause_is_not_duplicated():
    plan = PLAN + [{"Stunde": "3. 09:40:00 - 10:25:00"}]
    items, _, _ = normal([
        event(),
        event("09:20", "09:40", "Unterricht", "Typ: event"),
        event("09:40", "10:25", "E", ""),
    ], [raw(), raw("*1.gr.Pa.", "", "event"), raw("3", "E")], plan)
    assert len([item for item in items if item.kind == "break"]) == 1


def test_empty_subject_event_is_not_cancelled():
    items, verified, _ = normal([event(summary="Unterricht", desc="Typ: event")], [raw(subject="", kind="event")])
    assert items[0].kind == "event" and items[0].status == "scheduled"
    assert day_summary(items, DAY, verified=bool(verified))["first_start"] is not None


def test_special_lesson_not_substitution():
    items, _, _ = normal([event(summary="🔁 KoWo", desc="Typ: specialLesson")], [raw(subject="KoWo", kind="specialLesson")])
    assert items[0].changes == ["special"]


@pytest.mark.parametrize("events", [[], [{"start":"2026-09-17","end":"2026-09-18","summary":"Ausflug"}],
                                   [event(end="07:00")], [event(start="bad")]])
def test_empty_invalid_all_day_never_proves_school_free(events):
    items, verified, _ = normal(events, [])
    summary = day_summary(items, DAY, verified=bool(verified))
    assert summary["school_day"] == "unknown" and not summary["routine_ready"]


def test_partial_calendar_not_ready():
    items, verified, _ = normal([event()], [raw(), raw("2", "M")])
    assert not verified
    assert not day_summary(items, DAY, verified=bool(verified))["routine_ready"]


def test_raw_and_calendar_conflict_not_ready():
    _, verified, issues = normal([event()], [raw(subject="M")])
    assert not verified and "calendar_raw_disagreement" in issues


def test_unknown_type_not_ready():
    items, verified, _ = normal([event(desc="Typ: futureNewType")], [raw(kind="futureNewType")])
    assert not day_summary(items, DAY, verified=bool(verified))["routine_ready"]


def test_all_cancelled_known_vs_unverified():
    items, _, _ = normal([event(summary="X D", desc="Typ: cancelledLesson")], [raw(kind="cancelledLesson")])
    assert day_summary(items, DAY, verified=True)["school_day"] == "no"
    assert day_summary(items, DAY, verified=False)["school_day"] == "unknown"


def test_replacement_same_period_not_doubled():
    items, verified, _ = normal([event(summary="🔁 M", desc="Typ: substitution\nUrsprünglich: D")],
                               [raw(kind="cancelledLesson"), raw(subject="M", kind="substitution")])
    assert len(items) == 1 and bool(verified)
    assert items[0].original == {"text":"D"}


def test_parallel_ambiguity_disables_routine():
    _, verified, issues = normal([event()], [raw(), raw(subject="M")])
    assert not verified
    assert "ambiguous_parallel_lessons" in issues


def test_sort_deduplicate_and_stable_ids():
    a, _, _ = normal([event("08:35", "09:20", "M", ""), event(), event()], [raw(), raw("2", "M")])
    b, _, _ = normal([event(), event("08:35", "09:20", "M", "")], [raw(), raw("2", "M")])
    p1 = payload(a, date(2026,9,14), DAY, provider="test", target="3c", fetched_at=NOW.isoformat())
    p2 = payload(b, date(2026,9,14), DAY, provider="test", target="3c", fetched_at=NOW.isoformat())
    assert p1 == p2 and len(a) == 2


def test_card_projection_hides_display_only():
    items, _, _ = normal([event()], [raw()])
    rows, table = card_rows(items, date(2026,9,14), show_room=False, show_teacher=False)
    assert rows[0]["cells"] == ["", "", "", "D", ""]
    assert table[0]["Do"] == "D"
    assert items[0].rooms == ["R1"] and items[0].teachers == ["T1"]


def test_card_projection_exposes_change_styles_with_cancellation_priority():
    monday = date(2026, 9, 14)
    changed = Lesson(str(DAY), NOW.isoformat(), (NOW + timedelta(minutes=45)).isoformat(),
                     period="1", subject="M", status="changed")
    cancelled = Lesson(str(DAY), NOW.isoformat(), (NOW + timedelta(minutes=45)).isoformat(),
                       period="1", subject="D", status="cancelled")
    rows, table = card_rows([changed, cancelled], monday)
    assert rows[0]["cell_styles"][3] == {
        "bg": "#d32f2f", "bg_alpha": 0.20,
        "color": "var(--error-color, #ff5252)",
    }
    assert table[0]["cell_styles"] == rows[0]["cell_styles"]


def test_card_projection_omits_styles_for_regular_lessons():
    items, _, _ = normal([event()], [raw()])
    rows, table = card_rows(items, date(2026, 9, 14))
    assert "cell_styles" not in rows[0]
    assert "cell_styles" not in table[0]


def test_daily_does_not_follow_display_week():
    items, verified, _ = normal([event()], [raw()])
    result = payload(items, date(2026,9,21), DAY, provider="test", target="3c", fetched_at=NOW.isoformat(), verified_days=verified)
    assert result["rows"] == [] and result["daily"]["today"]["first_start"]
    assert result["daily"]["today"]["date"] == "2026-09-17"


def test_week_sensor_contract_stays_below_recorder_limit():
    rows_table = [
        {"time": f"{hour}.", "start": "07:45", "end": "08:30",
         **{day: "Langes Fach\nRaum 123\nLehrkraft" for day in ("Mo", "Di", "Mi", "Do", "Fr")}}
        for hour in range(1, 23)
    ]
    data = {
        "schema_version": 1,
        "provider": "stundenplan24",
        "rows_table": rows_table,
        "rows": [{"duplicate": row} for row in rows_table],
        "lessons": [{"large": "x" * 500} for _ in range(50)],
        "meta": {
            "week_start": "20260921", "days": ["20260921", "20260922"],
            "class": "5a", "no_plan": False, "exact_cells_by_date_time": {"huge": "x" * 20000},
            "vplan_available_by_date": {str(i): True for i in range(100)},
        },
    }
    attrs = compact_week_attributes(data)
    assert set(attrs) == {"schema_version", "provider", "rows_table", "meta",
                          "week_start", "days", "class", "no_plan"}
    assert "exact_cells_by_date_time" not in attrs["meta"]
    assert len(json.dumps(attrs, ensure_ascii=False).encode("utf-8")) < 16384


def test_utc_timestamps_converted():
    e = event(); e.update(start="2026-09-17T05:45:00Z", end="2026-09-17T06:30:00Z")
    items, verified, _ = normal([e], [raw()])
    assert items[0].start.endswith("07:45:00+02:00") and verified


def test_no_assumed_times_without_slot_table():
    _, verified, _ = normal([event()], [raw()], [])
    assert not verified


class FakeServices:
    def __init__(self, response): self.response, self.calls = response, []
    async def async_call(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.response


def provider_fixture():
    config = {"calendar_entity":"calendar.child", "today_entity":"sensor.today", "tomorrow_entity":"sensor.tomorrow", "week_entity":"sensor.week", "target":"3c"}
    states = {"calendar.child":SimpleNamespace(state="off", attributes={}),
              "sensor.today":SimpleNamespace(state="Plan", attributes={"raw":{"lessons":[raw()],"date":NOW.isoformat()}}),
              "sensor.week":SimpleNamespace(state="KW38", attributes={"plan":PLAN})}
    services = FakeServices({"calendar.child":{"events":[event()]}})
    return SchulmanagerProvider(SimpleNamespace(states=states, services=services), config)


def test_provider_calls_only_read_service_and_keeps_today_when_browsing():
    p = provider_fixture()
    data = asyncio.run(p.fetch(date(2026,9,21), NOW))
    assert data["daily"]["today"]["routine_ready"]
    args, kw = p.hass.services.calls[0]
    assert args[:2] == ("calendar", "get_events") and kw == {"blocking":True,"return_response":True}
    assert args[2]["start_date_time"].startswith(str(DAY))


def test_provider_unavailable_is_failure_not_empty_day():
    p = provider_fixture(); p.hass.states["calendar.child"].state = "unavailable"
    with pytest.raises(ValueError): asyncio.run(p.fetch(DAY, NOW))


def test_malformed_response_is_failure():
    p = provider_fixture(); p.hass.services.response = {}
    with pytest.raises(ValueError): asyncio.run(p.fetch(DAY, NOW))


def test_stale_day_sensor_does_not_verify_today():
    p = provider_fixture()
    p.hass.states["sensor.today"].attributes["raw"]["lessons"][0]["date"] = "2026-09-16"
    assert not asyncio.run(p.fetch(DAY, NOW))["daily"]["today"]["routine_ready"]


def test_old_upstream_snapshot_not_refreshed_by_adapter_poll():
    p = provider_fixture()
    p.hass.states["sensor.today"].attributes["raw"]["date"] = (NOW - timedelta(hours=2)).isoformat()
    data = asyncio.run(p.fetch(DAY, NOW))
    assert not data["daily"]["today"]["routine_ready"]
    assert "source_freshness_unverified" in data["meta"]["issues"]


@pytest.mark.parametrize("age,ready", [(0, True), (3600, True), (4499, True), (4500, False), (4501, False), (-61, False)])
def test_hourly_source_freshness_boundary(age, ready):
    p = provider_fixture()
    stamp = NOW - timedelta(seconds=age)
    p.hass.states["sensor.today"].attributes["raw"]["date"] = stamp.isoformat()
    day = asyncio.run(p.fetch(DAY, NOW))["daily"]["today"]
    assert day["routine_ready"] is ready
    assert day["source_fresh"] is ready
    assert day["source_updated_at"] == stamp.isoformat()
    assert day["source_valid_until"] == (stamp + timedelta(minutes=75)).isoformat()


def test_adapter_poll_does_not_extend_source_deadline():
    p = provider_fixture()
    first = asyncio.run(p.fetch(DAY, NOW))["daily"]["today"]
    later = asyncio.run(p.fetch(DAY, NOW + timedelta(minutes=75)))["daily"]["today"]
    assert first["source_valid_until"] == later["source_valid_until"]
    assert first["routine_ready"] and not later["routine_ready"]


@pytest.mark.parametrize("stamp", [None, "invalid", ""])
def test_missing_source_timestamp_stays_blocked(stamp):
    p = provider_fixture()
    p.hass.states["sensor.today"].attributes["raw"]["date"] = stamp
    day = asyncio.run(p.fetch(DAY, NOW))["daily"]["today"]
    assert not day["routine_ready"] and not day["source_fresh"]
    assert day["source_valid_until"] is None


def test_tomorrow_timestamp_is_shifted_back_before_age_check():
    p = provider_fixture()
    tomorrow = DAY + timedelta(days=1)
    p.hass.states["sensor.tomorrow"] = SimpleNamespace(state="Plan", attributes={
        "raw": {"lessons": [raw(day=tomorrow)], "date": (NOW + timedelta(days=1, minutes=-60)).replace(tzinfo=None).isoformat()}})
    p.hass.services.response["calendar.child"]["events"].append(event(day=tomorrow))
    day = asyncio.run(p.fetch(DAY, NOW))["daily"]["tomorrow"]
    assert day["routine_ready"]
    assert day["source_updated_at"] == (NOW - timedelta(minutes=60)).isoformat()
    assert day["source_valid_until"] == (NOW + timedelta(minutes=15)).isoformat()


def test_hourly_freshness_does_not_override_parallel_ambiguity():
    p = provider_fixture()
    p.hass.states["sensor.today"].attributes["raw"]["date"] = (NOW - timedelta(minutes=60)).isoformat()
    p.hass.states["sensor.today"].attributes["raw"]["lessons"].append(raw(subject="Pool"))
    data = asyncio.run(p.fetch(DAY, NOW))
    assert data["daily"]["today"]["source_fresh"]
    assert not data["daily"]["today"]["routine_ready"]
    assert "ambiguous_parallel_lessons" in data["meta"]["issues"]


def test_teacher_conflict_disables_readiness():
    r = raw(); r['teacher'] = 'T2'
    _, verified, issues = normal([event()], [r])
    assert not verified and "calendar_raw_disagreement" in issues
