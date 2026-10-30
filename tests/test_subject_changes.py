from dataclasses import replace
from datetime import date

import pytest

from stundenplan24_week.model import Lesson, card_rows, compact_week_attributes, day_summary


DAY = date(2026, 10, 30)
MONDAY = date(2026, 10, 26)


def changed(**kwargs):
    values = dict(date=str(DAY), start=f"{DAY}T08:00:00+01:00", end=f"{DAY}T08:45:00+01:00",
                  period="1", subject="E", rooms=["204", "205"], teachers=["NEW"],
                  status="changed", changes=["subject", "room", "teacher"], notes=["Workbook"],
                  original={"subject": "M", "rooms": ["101"], "teachers": ["OLD"]})
    return Lesson(**(values | kwargs))


def test_comparison_is_display_only_and_reaches_compact_sensor():
    lesson = changed()
    rows, table = card_rows([lesson], MONDAY, show_teacher=True)
    expected = {"Fr": [{"current": "E (ge\u00e4ndert)\n204\n205\nNEW\nWorkbook",
                        "original": "M\n101\nOLD"}]}
    assert rows[0]["subject_changes"] == table[0]["subject_changes"] == expected
    assert table[0]["Fr"] == expected["Fr"][0]["current"]
    assert len(rows) == len(table) == 1
    assert compact_week_attributes({"rows_table": table})["rows_table"][0]["subject_changes"] == expected
    summary = day_summary([lesson], DAY)
    assert summary["subjects"] == ["E"]
    assert summary["cancelled_count"] == 0 and len(summary["lessons"]) == 1
    assert summary["first_start"] == lesson.start and summary["last_end"] == lesson.end


@pytest.mark.parametrize("patch", [
    {"changes": ["room"]}, {"changes": ["teacher"]}, {"original": None},
    {"original": {"subject": " E "}}, {"original": {"subject": 42}},
    {"original": {}}, {"status": "cancelled"}, {"kind": "event"},
])
def test_non_subject_changes_keep_existing_shape(patch):
    rows, table = card_rows([changed(**patch)], MONDAY)
    assert "subject_changes" not in rows[0] and "subject_changes" not in table[0]


@pytest.mark.parametrize("room,teacher", [(False, False), (False, True), (True, False), (True, True)])
def test_visibility_settings_apply_to_both_halves(room, teacher):
    _, table = card_rows([changed()], MONDAY, show_room=room, show_teacher=teacher)
    pair = table[0]["subject_changes"]["Fr"][0]
    assert ("101" in pair["original"]) == room
    assert ("204" in pair["current"]) == room
    assert ("OLD" in pair["original"]) == teacher
    assert ("NEW" in pair["current"]) == teacher


def test_parallel_lessons_keep_independent_comparisons():
    first = changed()
    second = replace(first, subject="BIO", original={"subject": "D"}, course_id="other")
    _, table = card_rows([first, second], MONDAY)
    comparisons = table[0]["subject_changes"]["Fr"]
    assert len(comparisons) == 2
    assert {pair["original"].splitlines()[0] for pair in comparisons} == {"M", "D"}
    assert set(table[0]["Fr"].split("\n\n")) == {pair["current"] for pair in comparisons}
