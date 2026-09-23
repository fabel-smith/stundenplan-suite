"""Provider boundary, including a compatibility adapter for Stundenplan24."""
from __future__ import annotations

from datetime import date, datetime
from typing import Protocol
import re

from .coordinator import SPlanCoordinator
from .model import Lesson, payload


class Provider(Protocol):
    name: str

    async def fetch(self, monday: date, now: datetime) -> dict: ...


def normalize_stundenplan24(bundles: dict, zone) -> list[Lesson]:
    lessons = []
    for day, bundle in sorted(bundles.items()):
        base, overlays = bundle[:2]
        hours = sorted({x[0] for x in [*base, *overlays]})
        for hour in hours:
            originals = [x for x in base if x[0] == hour]
            changes = [x for x in overlays if x[0] == hour]
            for item in changes or originals:
                _, text, teacher, room, start, end = item
                original = originals[0] if len(originals) == 1 else None
                if original:
                    start, end = start or original[4], end or original[5]
                def stamp(value):
                    try:
                        return datetime.fromisoformat(f"{day}T{value}").replace(tzinfo=zone).isoformat() if value else None
                    except ValueError:
                        return None
                clean = text.replace("[[sp-red]]", "").strip()
                cancelled = bool(re.search(r"fällt\s+aus|entfällt", clean, re.I))
                moved = bool(re.search(r"verlegt|verschoben", clean, re.I))
                status = "cancelled" if cancelled else "changed" if changes else "scheduled"
                # Legacy XML parsing merges subject and notes and lacks reliable
                # completeness flags. Expose structured data, not false certainty.
                lines = clean.splitlines()
                lessons.append(Lesson(
                    day, stamp(start), stamp(end), str(hour),
                    subject=lines[0] if lines else "", teachers=[teacher] if teacher else [],
                    rooms=[room] if room else [], status=status,
                    changes=["cancellation"] if cancelled else ["move"] if moved else ["overlay"] if changes else [],
                    notes=lines[1:], confidence="inferred", source_type="stundenplan24_xml",
                    original={"subject": original[1], "teacher": original[2], "room": original[3]} if changes and original else None,
                ))
    return lessons


class _CapturingLegacyCoordinator(SPlanCoordinator):
    """Retain the original formatter while capturing pre-display lesson tuples."""

    async def _fetch_day_bundle(self, week_monday, day_dt, use_current_week_mode):
        result = await super()._fetch_day_bundle(week_monday, day_dt, use_current_week_mode)
        self.bundles[day_dt.date().isoformat()] = result
        return result


class Stundenplan24Provider:
    name = "stundenplan24"

    def __init__(self, hass, entry):
        self.legacy = _CapturingLegacyCoordinator(hass, entry)

    async def fetch(self, monday: date, now: datetime) -> dict:
        current_monday = now.date().fromordinal(now.date().toordinal() - now.weekday())
        self.legacy.week_offset = (monday - current_monday).days // 7
        self.legacy.bundles = {}
        legacy = await self.legacy._async_update_data()
        lessons = normalize_stundenplan24(self.legacy.bundles, now.tzinfo)
        result = payload(lessons, monday, now.date(), provider=self.name,
                         target=self.legacy.target, fetched_at=now.isoformat(),
                         issues=["legacy_completeness_unverified"])
        # Existing card output stays byte-for-byte equivalent at the value level.
        result.update(legacy)
        result["meta"] = {**legacy["meta"], "provider": self.name,
                          "fetched_at": now.isoformat(), "coverage": "unverified",
                          "issues": ["legacy_completeness_unverified"]}
        return result
