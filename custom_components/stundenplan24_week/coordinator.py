from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .stundenplan24_api import Stundenplan24Api
from .parser import parse_plan_klassen_xml  # (xml_text, target_class, show_room, show_teacher) -> list[tuple]
from .parser_wplan import parse_wplan_xml  # (xml_text, target_class) -> dict[(day_num, hour)] = info

_LOGGER = logging.getLogger(__name__)

CONF_SCHOOL_ID = "school_id"
CONF_TARGET = "target"  # Klasse, z.B. "05a"
CONF_SHOW_ROOM = "show_room"
CONF_SHOW_TEACHER = "show_teacher"

CONF_UPDATE_MINUTES = "update_minutes"
DEFAULT_UPDATE_MINUTES = 360  # alle 6h

CONF_WPLAN_ENABLED = "wplan_enabled"
CONF_WPLAN_DAYS = "wplan_days"
CONF_SHOW_SUB_TEXT = "show_substitution_text"

DEFAULT_WPLAN_ENABLED = False
DEFAULT_WPLAN_DAYS = 3


def ymd(d: datetime) -> str:
    return d.strftime("%Y%m%d")


def monday_of_week(now: datetime) -> datetime:
    d = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return d - timedelta(days=d.weekday())  # weekday: Mo=0


def target_variants(target: str) -> List[str]:
    """Stundenplan24 Klassen sind manchmal '5a' und manchmal '05a'. Wir versuchen beides."""
    t = (target or "").strip()
    if not t:
        return []
    out = [t]
    if len(t) >= 2 and t[0] == "0" and t[1].isdigit():
        out.append(t.lstrip("0"))  # "05a" -> "5a"
    if len(t) >= 2 and t[0].isdigit() and t[1].isalpha() and not t.startswith("0"):
        out.append("0" + t)  # "5a" -> "05a"

    seen = set()
    uniq: List[str] = []
    for x in out:
        if x not in seen:
            uniq.append(x)
            seen.add(x)
    return uniq


def _format_text(text: str) -> List[str]:
    """
    Produktionsreife Formatierung für Stundenplan24:
    - trennt bei ';' und vorhandenen Zeilenumbrüchen
    - 🔴 bei 'fällt aus'
    - 🟠 bei 'verlegt'
    - ⚠️ bei Sondertagen (Präventionstag, Zeugnisausgabe, Projekttag, Vorabitur, ...)
    Marker stehen IMMER am Zeilenanfang.
    """
    import re

    t = (text or "").strip()
    if not t:
        return []

    # Sondertag-Schlüsselwörter (erweiterbar)
    SPECIAL_DAY_PATTERNS = [
        r"präventionstag",
        r"zeugnisausgabe",
        r"projekttag",
        r"vorabitur",
        r"prüfung",
        r"nachtermin",
        r"schulfrei",
    ]

    lines: List[str] = []

    # Erst bestehende Zeilen respektieren, dann bei ';' splitten
    for raw_line in t.splitlines():
        parts = [p.strip() for p in raw_line.split(";") if p.strip()]
        lines.extend(parts if parts else [raw_line.strip()])

    out: List[str] = []
    for line in lines:
        l = line.strip()
        if not l:
            continue

        low = l.lower()

        # 🔴 fällt aus
        if re.search(r"\bfällt\s+aus\b", low):
            l = f"🔴 {l}"

        # 🟠 verlegt
        elif re.search(r"\bverlegt\b", low):
            l = f"🟠 {l}"

        # ⚠️ Sondertage
        elif any(re.search(pat, low) for pat in SPECIAL_DAY_PATTERNS):
            l = f"⚠️ {l}"

        out.append(l)

    return out



class SPlanCoordinator(DataUpdateCoordinator[Dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry

        self.school_id: str = (entry.data.get(CONF_SCHOOL_ID) or "").strip()
        self.username: str = (entry.data.get("username") or "").strip()
        self.password: str = (entry.data.get("password") or "").strip()
        self.target: str = (entry.data.get(CONF_TARGET) or "").strip()

        # options überschreibt data (ohne "or"-Fallen)
        self.show_room: bool = bool(entry.options.get(CONF_SHOW_ROOM, entry.data.get(CONF_SHOW_ROOM, True)))
        self.show_teacher: bool = bool(entry.options.get(CONF_SHOW_TEACHER, entry.data.get(CONF_SHOW_TEACHER, False)))

        self.wplan_enabled: bool = bool(entry.options.get(CONF_WPLAN_ENABLED, entry.data.get(CONF_WPLAN_ENABLED, DEFAULT_WPLAN_ENABLED)))
        self.wplan_days: int = int(entry.options.get(CONF_WPLAN_DAYS, entry.data.get(CONF_WPLAN_DAYS, DEFAULT_WPLAN_DAYS)))
        self.show_sub_text: bool = bool(entry.options.get(CONF_SHOW_SUB_TEXT, entry.data.get(CONF_SHOW_SUB_TEXT, True)))

        update_minutes = int(entry.options.get(CONF_UPDATE_MINUTES, DEFAULT_UPDATE_MINUTES))

        self.api = Stundenplan24Api(hass, self.username, self.password)

        super().__init__(
            hass,
            logger=_LOGGER,
            name=f"stundenplan24_week_{self.target}",
            update_interval=timedelta(minutes=update_minutes),
        )

    async def _fetch_day_lessons(self, day_dt: datetime) -> List[Tuple[int, str, str, str, str, str]]:
        """(stunde:int, fach:str, lehrer:str, raum:str, start:str, end:str)"""
        url = f"https://www.stundenplan24.de/{self.school_id}/mobil/mobdaten/PlanKl{ymd(day_dt)}.xml"
        xml_text = await self.api.fetch_text(url)

        last: List[Tuple[int, str, str, str, str, str]] = []
        for tv in target_variants(self.target):
            lessons = parse_plan_klassen_xml(
                xml_text,
                target_class=tv,
                show_room=self.show_room,
                show_teacher=self.show_teacher,
            )
            last = lessons or []
            if last:
                if tv != self.target:
                    _LOGGER.debug("Klassen-Alias genutzt (PlanKl): %s -> %s", self.target, tv)
                return last
        return last

    async def _fetch_wplan_info(self, day_dt: datetime) -> Dict[Tuple[int, int], str]:
        """
        Holt WPlanKlYYYYMMDD.xml (Vertretungsplan) und gibt mapping (day_num,hour)->info_text.
        Wichtig: 404 ist normal (kein Vertretungsplan an dem Tag) -> {}.
        """
        url = f"https://www.stundenplan24.de/{self.school_id}/mobil/mobdaten/WPlanKl{ymd(day_dt)}.xml"
        try:
            xml_text = await self.api.fetch_text(url)
        except Exception as e:
            msg = str(e)
            if "404" in msg or "Not Found" in msg:
                _LOGGER.debug("Kein WPlan vorhanden für %s (%s)", ymd(day_dt), url)
                return {}
            raise

        for tv in target_variants(self.target):
            info_map = parse_wplan_xml(xml_text, target_class=tv)
            if info_map:
                if tv != self.target:
                    _LOGGER.debug("Klassen-Alias genutzt (WPlan): %s -> %s", self.target, tv)
                return info_map
        return {}

    async def _async_update_data(self) -> Dict[str, Any]:
        try:
            now = datetime.now()
            monday = monday_of_week(now)
            day_dates = [monday + timedelta(days=i) for i in range(5)]  # Mo..Fr

            by_hour: Dict[int, Dict[str, Any]] = {}

            def to_min(t: str) -> Optional[int]:
                t = (t or "").strip()
                if not t or ":" not in t:
                    return None
                try:
                    hh, mm = t.split(":", 1)
                    return int(hh) * 60 + int(mm)
                except Exception:
                    return None

            def to_hhmm(m: int) -> str:
                return f"{m//60:02d}:{m%60:02d}"

            time_minmax: Dict[int, Tuple[Optional[int], Optional[int]]] = {}

            # 1) Grundplan (PlanKl)
            for col_idx, day_dt in enumerate(day_dates):
                lessons = await self._fetch_day_lessons(day_dt)

                for (stunde, fach, lehrer, raum, start, end) in lessons:
                    if not stunde or stunde <= 0:
                        continue

                    row = by_hour.get(stunde)
                    if not row:
                        row = {"time": f"{stunde}.", "start": "", "end": "", "cells": ["", "", "", "", ""]}
                        by_hour[stunde] = row

                    # Zeiten min/max sammeln
                    smin = to_min(start)
                    emin = to_min(end)
                    cur_s, cur_e = time_minmax.get(stunde, (None, None))
                    if smin is not None:
                        cur_s = smin if cur_s is None else min(cur_s, smin)
                    if emin is not None:
                        cur_e = emin if cur_e is None else max(cur_e, emin)
                    time_minmax[stunde] = (cur_s, cur_e)

                    fach = (fach or "").strip()
                    lehrer = (lehrer or "").strip()
                    raum = (raum or "").strip()

                    # Reihenfolge wie Stundenplan24: Fach / Raum / Lehrer (jeweils eigene Zeile)
                    lines: List[str] = []
                    lines.extend(_format_text(fach))  # inkl. ';'->\n und 🔴 bei "fällt aus"

                    if self.show_room and raum:
                        lines.append(raum)
                    if self.show_teacher and lehrer:
                        lines.append(lehrer)

                    cell = "\n".join([l for l in lines if l]).strip()
                    if not cell:
                        continue

                    cur = (row["cells"][col_idx] or "").strip()
                    if cur and cell and cell not in cur:
                        row["cells"][col_idx] = f"{cur}\n{cell}".strip()
                    elif not cur:
                        row["cells"][col_idx] = cell

            if not by_hour:
                raise UpdateFailed(
                    "Keine Daten gefunden. Prüfe SchulID/Klasse/Login."
                    f" Klasse probiert: {', '.join(target_variants(self.target))}"
                )

            # 2) WPlan mergen (wenn aktiv)  ✅ (Zeilenumbruch bei ';' + 🔴 pro Ausfallzeile)
            if self.wplan_enabled and self.show_sub_text:
                for day_dt in day_dates:
                    info_map = await self._fetch_wplan_info(day_dt)
                    if not info_map:
                        continue

                    for (day_num, hour), info in info_map.items():
                        if day_num < 1 or day_num > 5:
                            continue
                        col_idx = day_num - 1

                        if not hour or hour <= 0:
                            continue

                        info_lines = _format_text(info)
                        if not info_lines:
                            continue

                        row = by_hour.get(hour)
                        if not row:
                            row = {"time": f"{hour}.", "start": "", "end": "", "cells": ["", "", "", "", ""]}
                            by_hour[hour] = row

                        base_cell = (row["cells"][col_idx] or "").strip()
                        base_lines = [l.strip() for l in base_cell.splitlines() if l.strip()] if base_cell else []

                        # Duplikate vermeiden (zeilenweise)
                        for il in info_lines:
                            if il not in base_lines:
                                base_lines.append(il)

                        row["cells"][col_idx] = "\n".join(base_lines).strip()

            # Zeiten eintragen
            for h, row in by_hour.items():
                s, e = time_minmax.get(h, (None, None))
                if s is not None:
                    row["start"] = to_hhmm(s)
                if e is not None:
                    row["end"] = to_hhmm(e)

            hours = sorted(by_hour.keys())
            rows = [by_hour[h] for h in hours]

            # Zellen trimmen
            for row in rows:
                row["cells"] = [c.strip() if c and c.strip() else "" for c in row["cells"]]

            return {
                "rows": rows,
                "meta": {
                    "school_id": self.school_id,
                    "class": self.target,
                    "week_start": ymd(monday),
                    "days": [ymd(d) for d in day_dates],
                    "show_room": self.show_room,
                    "show_teacher": self.show_teacher,
                    "wplan_enabled": self.wplan_enabled,
                    "wplan_days": self.wplan_days,
                    "source": "mobil/mobdaten (PlanKlYYYYMMDD.xml) + optional WPlanKlYYYYMMDD.xml",
                },
            }

        except Exception as e:
            raise UpdateFailed(str(e)) from e
