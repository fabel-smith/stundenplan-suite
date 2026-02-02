from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .stundenplan24_api import Stundenplan24Api
from .parser import parse_plan_klassen_xml  # muss: (xml_text, target_class, show_room, show_teacher) -> list[tuple]

_LOGGER = logging.getLogger(__name__)

CONF_SCHOOL_ID = "school_id"
CONF_TARGET = "target"            # Klasse, z.B. "05a"
CONF_SHOW_ROOM = "show_room"
CONF_SHOW_TEACHER = "show_teacher"

DEFAULT_UPDATE_MINUTES = 360  # alle 6h reicht normalerweise locker


def ymd(d: datetime) -> str:
    return d.strftime("%Y%m%d")


def monday_of_week(now: datetime) -> datetime:
    # Mo 00:00 (lokal)
    d = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return d - timedelta(days=d.weekday())  # weekday: Mo=0


def target_variants(target: str) -> List[str]:
    """
    Stundenplan24 Klassen sind manchmal "5a" und manchmal "05a".
    Wir versuchen beides, ohne den Nutzer zu nerven.
    """
    t = (target or "").strip()
    if not t:
        return []
    out = [t]
    # führende Null bei Klassenstufe entfernen: "05a" -> "5a"
    if len(t) >= 2 and t[0] == "0" and t[1].isdigit():
        out.append(t.lstrip("0"))
    # umgekehrt: "5a" -> "05a" (nur wenn es so aussieht wie "5a")
    if len(t) >= 2 and t[0].isdigit() and t[1].isalpha() and not t.startswith("0"):
        out.append("0" + t)
    # unique, Reihenfolge behalten
    seen = set()
    uniq: List[str] = []
    for x in out:
        if x not in seen:
            uniq.append(x)
            seen.add(x)
    return uniq


class SPlanCoordinator(DataUpdateCoordinator[Dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry

        self.school_id: str = entry.data[CONF_SCHOOL_ID]
        self.username: str = entry.data.get("username", "")
        self.password: str = entry.data.get("password", "")

        self.target: str = entry.data[CONF_TARGET]
        self.show_room: bool = entry.data.get(CONF_SHOW_ROOM, True)
        self.show_teacher: bool = entry.data.get(CONF_SHOW_TEACHER, False)

        self.api = Stundenplan24Api(hass, self.username, self.password)

        update_minutes = None
        if entry.options:
            update_minutes = entry.options.get("update_minutes")
        if not update_minutes:
            update_minutes = DEFAULT_UPDATE_MINUTES

        super().__init__(
            hass,
            logger=_LOGGER,
            name=f"stundenplan24_week_{self.target}",
            update_interval=timedelta(minutes=int(update_minutes)),
        )

    async def _fetch_day_lessons(self, day_dt: datetime) -> List[Tuple[int, str, str, str, str, str]]:
        """
        Liefert Lessons für EINEN Tag, gefiltert auf Klasse.
        Rückgabe-Format (wie in deinem bisherigen Code):
          (stunde:int, fach:str, lehrer:str, raum:str, start:str, end:str)
        """
        url = f"https://www.stundenplan24.de/{self.school_id}/mobil/mobdaten/PlanKl{ymd(day_dt)}.xml"
        xml_text = await self.api.fetch_text(url)

        # Klasse in Varianten probieren (05a vs 5a)
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
                    _LOGGER.debug("Klassen-Alias genutzt: %s -> %s", self.target, tv)
                return last

        return last  # leer

    async def _async_update_data(self) -> Dict[str, Any]:
        try:
            now = datetime.now()
            monday = monday_of_week(now)
            day_dates = [monday + timedelta(days=i) for i in range(5)]  # Mo..Fr

            # hour -> row dict
            by_hour: Dict[int, Dict[str, Any]] = {}

            # Wir sammeln Zeiten robust: pro Stunde min(start), max(end)
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

            # pro Stunde: start_min, end_min
            time_minmax: Dict[int, Tuple[Optional[int], Optional[int]]] = {}

            for col_idx, day_dt in enumerate(day_dates):
                lessons = await self._fetch_day_lessons(day_dt)

                for (stunde, fach, lehrer, raum, start, end) in lessons:
                    if not stunde or stunde <= 0:
                        continue

                    row = by_hour.get(stunde)
                    if not row:
                        row = {
                            "time": f"{stunde}.",
                            "start": "",
                            "end": "",
                            "cells": ["", "", "", "", ""],  # Mo..Fr
                        }
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

                    # Zellinhalt: Fach + optional (Raum/Lehrer)
                    fach = (fach or "").strip()
                    lehrer = (lehrer or "").strip()
                    raum = (raum or "").strip()

                    extras: List[str] = []
                    if self.show_room and raum:
                        extras.append(raum)
                    if self.show_teacher and lehrer:
                        extras.append(lehrer)

                    cell = fach
                    if cell and extras:
                        cell = f"{cell} ({' · '.join(extras)})"

                    cur = row["cells"][col_idx] or ""
                    if cur and cell and cell not in cur:
                        row["cells"][col_idx] = f"{cur} / {cell}"
                    elif not cur:
                        row["cells"][col_idx] = cell

            if not by_hour:
                raise UpdateFailed(
                    f"Keine Daten gefunden. Prüfe SchulID/Klasse/Login. Klasse probiert: {', '.join(target_variants(self.target))}"
                )

            # Zeiten in rows eintragen
            for h, row in by_hour.items():
                s, e = time_minmax.get(h, (None, None))
                if s is not None:
                    row["start"] = to_hhmm(s)
                if e is not None:
                    row["end"] = to_hhmm(e)

            hours = sorted(by_hour.keys())
            rows = [by_hour[h] for h in hours]

            return {
                "rows": rows,
                "meta": {
                    "school_id": self.school_id,
                    "class": self.target,
                    "week_start": ymd(monday),
                    "days": [ymd(d) for d in day_dates],
                    "show_room": self.show_room,
                    "show_teacher": self.show_teacher,
                    "source": "mobil/mobdaten (PlanKlYYYYMMDD.xml)",
                },
            }

        except Exception as e:
            raise UpdateFailed(str(e)) from e
