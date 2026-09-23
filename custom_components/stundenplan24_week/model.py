"""Provider-independent, JSON-serializable timetable contract (version 1).

No Home Assistant imports: parsers, projections and morning logic can be tested
without a running installation. Unknown is deliberately different from false.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from hashlib import sha256
from typing import Any

SCHEMA_VERSION = 1
DAYS = ("Mo", "Di", "Mi", "Do", "Fr")
CARD_META_KEYS = (
    "week_start", "days", "class", "school_id", "no_plan", "updated_days",
    "updated_raw", "updated_error", "source", "provider", "fetched_at",
    "source_updated_at", "coverage", "issues", "week_offset",
)
CELL_STYLES = {
    "cancelled": {
        "bg": "#d32f2f", "bg_alpha": 0.20,
        "color": "var(--error-color, #ff5252)",
    },
    "changed": {
        "bg": "#f9a825", "bg_alpha": 0.18,
        "color": "var(--warning-color, #ffb300)",
    },
}
STYLE_PRIORITY = {"changed": 1, "cancelled": 2}


@dataclass
class Lesson:
    date: str
    start: str | None
    end: str | None
    period: str = ""
    subject: str = ""
    subject_full: str = ""
    teachers: list[str] = field(default_factory=list)
    rooms: list[str] = field(default_factory=list)
    kind: str = "lesson"  # lesson, break, event, unknown
    status: str = "scheduled"  # scheduled, cancelled, changed, unknown
    changes: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    original: dict[str, Any] | None = None
    source_type: str = ""
    confidence: str = "reported"  # reported, corroborated, inferred, unknown
    source_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        # Stable under input reordering; no personal source IDs are needed.
        identity = [self.source_id, self.date, self.period, self.start, self.end,
                    self.subject, self.teachers, self.rooms, self.kind, self.status]
        data["id"] = sha256(repr(identity).encode()).hexdigest()[:20]
        return data


def ordered(lessons: list[Lesson]) -> list[Lesson]:
    return sorted(lessons, key=lambda x: (x.date, x.start or "99", x.period, x.subject))


def day_summary(lessons: list[Lesson], day: date, *, verified: bool = False,
                fetched_at: str | None = None) -> dict[str, Any]:
    items = ordered([x for x in lessons if x.date == day.isoformat()])
    active = [x for x in items if x.kind in ("lesson", "event")
              and x.status not in ("cancelled", "unknown")]
    cancelled = [x for x in items if x.status == "cancelled"]
    uncertain = any(x.kind == "unknown" or x.status == "unknown" or
                    (x.status != "cancelled" and x.kind != "break" and
                     (not x.start or not x.end)) for x in items)
    timed = [x for x in active if x.start and x.end]
    first = min((x.start for x in timed), default=None)
    last = max((x.end for x in timed), default=None)
    # An empty feed cannot prove a holiday, even on a weekday.
    school_day = "yes" if active else ("no" if verified and cancelled and not uncertain else "unknown")
    earliest = min((x.start for x in items if x.kind != "break" and x.start), default=None)
    first_cancelled = (any(x.start == earliest for x in cancelled)
                       and not any(x.start == earliest for x in active)) if earliest else None
    return {
        "date": day.isoformat(), "school_day": school_day,
        "first_start": first, "last_end": last,
        "subjects": [x.subject_full or x.subject for x in active if x.subject_full or x.subject],
        "lessons": [x.to_dict() for x in items],
        "cancelled_count": len(cancelled),
        "has_changes": any(x.changes or x.status in ("changed", "cancelled") for x in items),
        "first_lesson_cancelled": first_cancelled,
        "routine_ready": bool(verified and timed and not uncertain and
                              all(x.confidence == "corroborated" for x in active)),
        "coverage": "corroborated" if verified else "unverified",
        "fetched_at": fetched_at,
    }


def card_rows(lessons: list[Lesson], monday: date, *, show_room: bool = True,
              show_teacher: bool = False) -> tuple[list[dict], list[dict]]:
    grid: dict[tuple[str, str, str], dict] = {}
    for item in ordered(lessons):
        dt = date.fromisoformat(item.date)
        col = (dt - monday).days
        if not 0 <= col < 5:
            continue
        start = datetime.fromisoformat(item.start).strftime("%H:%M") if item.start else ""
        end = datetime.fromisoformat(item.end).strftime("%H:%M") if item.end else ""
        label = f"{item.period}." if item.period.isdigit() else (item.period or f"{start}–{end}")
        key = (start, end, label)
        row = grid.setdefault(key, {"time": label, "start": start, "end": end,
                                    "kind": item.kind, "cells": [""] * 5,
                                    "cell_styles": [None] * 5,
                                    "style_priorities": [0] * 5})
        text = item.subject or ("Pause" if item.kind == "break" else "Veranstaltung" if item.kind == "event" else "Unterricht")
        if item.status == "cancelled":
            text = "Entfällt: " + text
        elif item.status == "changed":
            text += " (geändert)"
        parts = [text]
        if show_room:
            parts.extend(item.rooms)
        if show_teacher:
            parts.extend(item.teachers)
        parts.extend(item.notes)
        cell = "\n".join(x for x in parts if x)
        row["cells"][col] = "\n\n".join(x for x in (row["cells"][col], cell) if x)
        priority = STYLE_PRIORITY.get(item.status, 0)
        if priority > row["style_priorities"][col]:
            row["cell_styles"][col] = CELL_STYLES.get(item.status)
            row["style_priorities"][col] = priority
    rows = []
    for key in sorted(grid):
        row = grid[key]
        if row["kind"] == "break":
            rows.append({"break": True, "time": f'{row["start"]}–{row["end"]}',
                         "start": row["start"], "end": row["end"], "label": "Pause"})
        else:
            projected = {k: v for k, v in row.items()
                         if k not in ("kind", "style_priorities", "cell_styles")}
            if any(row["cell_styles"]):
                projected["cell_styles"] = row["cell_styles"]
            rows.append(projected)
    table = [dict(r) if r.get("break") else
             {"time": r["time"], "start": r["start"], "end": r["end"],
              **dict(zip(DAYS, r["cells"])),
              **({"cell_styles": r["cell_styles"]} if "cell_styles" in r else {})}
             for r in rows]
    return rows, table


def compact_week_attributes(data: dict[str, Any]) -> dict[str, Any]:
    """Return the non-duplicated sensor contract consumed by the card.

    Home Assistant stores the complete attribute mapping in the recorder. Older
    versions exposed the same timetable and metadata under several aliases and
    JSON strings, which could exceed the recorder's 16 KiB attribute limit.
    """
    source_meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    meta = {key: source_meta[key] for key in CARD_META_KEYS if key in source_meta}
    attrs: dict[str, Any] = {
        "schema_version": data.get("schema_version", SCHEMA_VERSION),
        "provider": data.get("provider"),
        "rows_table": data.get("rows_table") or [],
        "meta": meta,
    }
    for key in ("week_start", "days", "class", "school_id", "no_plan"):
        if key in meta:
            attrs[key] = meta[key]
    return attrs


def payload(lessons: list[Lesson], monday: date, today: date, *, provider: str,
            target: str, fetched_at: str, verified_days: set[str] | None = None,
            show_room: bool = True, show_teacher: bool = False,
            issues: list[str] | None = None) -> dict[str, Any]:
    verified_days = verified_days or set()
    rows, table = card_rows(lessons, monday, show_room=show_room, show_teacher=show_teacher)
    daily = {label: day_summary(lessons, day, verified=day.isoformat() in verified_days,
                                fetched_at=fetched_at)
             for label, day in (("today", today), ("tomorrow", today + timedelta(days=1)))}
    return {
        "schema_version": SCHEMA_VERSION, "provider": provider,
        "lessons": [x.to_dict() for x in ordered(lessons)], "daily": daily,
        "rows": rows, "rows_table": table,
        "meta": {"class": target, "week_start": monday.strftime("%Y%m%d"),
                 "days": [(monday + timedelta(days=i)).strftime("%Y%m%d") for i in range(5)],
                 "no_plan": not rows, "source": provider, "fetched_at": fetched_at,
                 "source_updated_at": None, "coverage": "unverified",
                 "issues": sorted(set(issues or [])),
                 "week_offset": (monday - (today - timedelta(days=today.weekday()))).days // 7},
    }
