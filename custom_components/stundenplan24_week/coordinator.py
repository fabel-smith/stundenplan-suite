from __future__ import annotations

import asyncio
import logging
import re
from xml.etree import ElementTree as ET
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .parser import parse_plan_klassen_xml
from .parser_wplan import parse_wplan_xml
from .parser_wplan_html import parse_wplan_html_to_rows
from .stundenplan24_api import Stundenplan24Api

_LOGGER = logging.getLogger(__name__)

CONF_SCHOOL_ID = "school_id"
CONF_TARGET = "target"
CONF_SHOW_ROOM = "show_room"
CONF_SHOW_TEACHER = "show_teacher"

CONF_UPDATE_MINUTES = "update_minutes"
DEFAULT_UPDATE_MINUTES = 360  # alle 6h

CONF_WPLAN_ENABLED = "wplan_enabled"
CONF_WPLAN_DAYS = "wplan_days"
CONF_SHOW_SUB_TEXT = "show_substitution_text"

DEFAULT_WPLAN_ENABLED = False
DEFAULT_WPLAN_DAYS = 3


# -----------------------------
# Helpers
# -----------------------------
def ymd(d: datetime) -> str:
    return d.strftime("%Y%m%d")


def monday_of_week(now: datetime) -> datetime:
    d = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return d - timedelta(days=d.weekday())  # Mo=0


def weekdays_for_monday(monday_dt: datetime) -> List[datetime]:
    return [monday_dt + timedelta(days=i) for i in range(5)]


def target_variants(target: str) -> List[str]:
    """Robuste Varianten: 09c/9c, Case-Varianten."""
    t = (target or "").strip()
    if not t:
        return []

    variants: set[str] = set()

    def add(x: str) -> None:
        x = (x or "").strip()
        if x:
            variants.add(x)
            variants.add(x.lower())
            variants.add(x.upper())

    add(t)

    # 09c -> 9c
    if len(t) >= 2 and t[0] == "0" and t[1].isdigit():
        add(t.lstrip("0"))

    # 9c -> 09c
    m = re.match(r"^(\d)([a-zA-Z].*)$", t)
    if m and not t.startswith("0"):
        add(f"0{m.group(1)}{m.group(2)}")

    return list(variants)


def _format_text(text: str) -> List[str]:
    """Zeilen normalisieren + simple Markierungen (🔴 bei Ausfall, 🟠 bei Verlegung)."""
    t = (text or "").strip()
    if not t:
        return []

    lines: List[str] = []
    for raw_line in t.splitlines():
        parts = [p.strip() for p in raw_line.split(";") if p.strip()]
        lines.extend(parts if parts else [raw_line.strip()])

    out: List[str] = []
    for line in lines:
        l = line.strip()
        if not l:
            continue
        low = l.lower()
        if re.search(r"\b(fällt\s+aus|entfällt)\b", low):
            l = f"🔴 {l}"
        elif re.search(r"\b(verlegt|verschoben)\b", low):
            l = f"🟠 {l}"
        out.append(l)

    # Duplikate vermeiden (Stundenplan24 liefert teils denselben Hinweis doppelt,

    # z.B. einmal mit Lehrername und einmal mit Kürzel).

    def _dedupe_key(s: str) -> str:

        x = (s or "").strip()

        x = re.sub(r"^[🟠🔴]\s*", "", x)

        # Entferne Lehrer-Kürzel / Fachkürzel (GEO, EN, G/R/W, etc.)

        x = re.sub(r"\b[A-ZÄÖÜ]{1,4}(?:/[A-ZÄÖÜ]{1,4}){1,3}\b", " ", x)

        x = re.sub(r"\b[A-ZÄÖÜ]{2,6}\b", " ", x)

        # Entferne 'Frau/Herr Name'

        x = re.sub(r"\b(Frau|Herr)\s+[A-Za-zÄÖÜäöüß\-]+\b", " ", x, flags=re.IGNORECASE)

        x = x.lower()

        x = re.sub(r"\s+", " ", x).strip()

        return x

    

    seen: set[str] = set()

    deduped: List[str] = []

    for l in out:

        k = _dedupe_key(l)

        if k and k in seen:

            continue

        if k:

            seen.add(k)

        deduped.append(l)

    

    return deduped
def _append_parallel(base: str, extra: str) -> str:
    """Wenn in derselben Stunde mehrere Gruppen parallel existieren, Inhalte untereinander anhängen."""
    b = (base or "").strip()
    e = (extra or "").strip()
    if not e:
        return b
    if not b:
        return e
    if e in b:
        return b
    return f"{b}\n\n{e}"


def _norm_ts(s: str) -> str:
    """Normalize timestamps like '17.02.2026 13:49' or '17.02.2026, 13:49' -> '17.02.2026, 13:49'."""
    if not s:
        return ""
    s = " ".join(str(s).strip().split())
    m = re.search(r"(\d{1,2}\.\d{1,2}\.\d{4})\s*,?\s*(\d{1,2}:\d{2})", s)
    if not m:
        return s
    return f"{m.group(1)}, {m.group(2)}"


def _extract_stand_from_xml(xml_text: str) -> str:
    """Best-effort extraction of an 'Stand/Aktualisiert' timestamp from Indiware XML."""
    if not xml_text:
        return ""
    m = re.search(r"<Stand>(.*?)</Stand>", xml_text, re.IGNORECASE | re.DOTALL)
    if m:
        return _norm_ts(m.group(1))
    m = re.search(r"<stand>(.*?)</stand>", xml_text, re.IGNORECASE | re.DOTALL)
    if m:
        return _norm_ts(m.group(1))
    # fallback: first date+time occurrence
    m = re.search(r"(\d{1,2}\.\d{1,2}\.\d{4})\s*,?\s*(\d{1,2}:\d{2})", xml_text)
    if m:
        return f"{m.group(1)}, {m.group(2)}"
    return ""


class OverlayType:
    NONE = 0
    CANCEL = 1
    MOVE = 2
    SUBSTITUTE = 3
    SPECIAL = 4


def _classify_overlay(txt: str) -> int:
    """Erkennt Art der Änderung im VPlan/WPlan."""
    t = (txt or "").strip().lower()
    if not t:
        return OverlayType.NONE

    if "fällt aus" in t or "entfällt" in t:
        return OverlayType.CANCEL
    if "verlegt" in t or "verschoben" in t:
        return OverlayType.MOVE
    if any(
        x in t
        for x in [
            "zeugnis",
            "präventionstag",
            "wandertag",
            "projekttag",
            "methodentag",
            "studientag",
            "unterrichtsfrei",
            "prüfung",
            "klausur",
        ]
    ):
        return OverlayType.SPECIAL
    if " für " in t or t.startswith("für "):
        return OverlayType.SUBSTITUTE
    if " statt " in t or t.startswith("statt "):
        return OverlayType.SUBSTITUTE

    return OverlayType.SUBSTITUTE



# -----------------------------
# Indiware Wochenplan Online (wplan/wdatenk) Helpers
# -----------------------------
def _parse_ddmmyyyy(s: str) -> Optional[datetime]:
    try:
        return datetime.strptime((s or "").strip(), "%d.%m.%Y")
    except Exception:
        return None


def _indiware_date_in_range(d: datetime, start_s: str, end_s: str) -> bool:
    ds = d.date()
    a = _parse_ddmmyyyy(start_s)
    b = _parse_ddmmyyyy(end_s)
    if not a or not b:
        return False
    return a.date() <= ds <= b.date()


def _ymd_to_dt(s: str) -> Optional[datetime]:
    try:
        return datetime.strptime((s or "").strip(), "%Y%m%d")
    except Exception:
        return None


def _url_indiware_basis(school_id: str) -> str:
    return f"https://www.stundenplan24.de/{school_id}/wplan/wdatenk/SPlanKl_Basis.xml"


def _url_indiware_sw(school_id: str, sw: int) -> str:
    return f"https://www.stundenplan24.de/{school_id}/wplan/wdatenk/SPlanKl_Sw{sw}.xml"

def _merge_cells(base: str, overlay: str) -> str:
    """Intelligentes Mergen von Basis-Stundenplan und Vertretung."""
    b = (base or "").strip()
    o = (overlay or "").strip()
    if not o:
        return b

    t = _classify_overlay(o)

    if t == OverlayType.CANCEL:
        return f"—\n{o}".strip()

    if t == OverlayType.MOVE:
        if b:
            b_lines = [x.strip() for x in b.splitlines() if x.strip()]
            o_lines = [x.strip() for x in o.splitlines() if x.strip()]
            for ln in o_lines:
                if ln not in b_lines:
                    b_lines.append(ln)
            return "\n".join(b_lines).strip()
        return o

    if t == OverlayType.SPECIAL:
        return o

    # SUBSTITUTE: ersetzt den Inhalt (Vertretungslehrer/Fach/Raum)
    return o


# -----------------------------
# Coordinator
# -----------------------------
class SPlanCoordinator(DataUpdateCoordinator[Dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry

        self.school_id: str = (entry.data.get(CONF_SCHOOL_ID) or "").strip()
        self.username: str = (entry.data.get("username") or "").strip()
        self.password: str = (entry.data.get("password") or "").strip()
        self.target: str = (entry.data.get(CONF_TARGET) or "").strip()

        self.show_room: bool = bool(entry.options.get(CONF_SHOW_ROOM, entry.data.get(CONF_SHOW_ROOM, True)))
        self.show_teacher: bool = bool(entry.options.get(CONF_SHOW_TEACHER, entry.data.get(CONF_SHOW_TEACHER, False)))

        self.wplan_enabled: bool = bool(entry.options.get(CONF_WPLAN_ENABLED, entry.data.get(CONF_WPLAN_ENABLED, DEFAULT_WPLAN_ENABLED)))
        self.wplan_days: int = int(entry.options.get(CONF_WPLAN_DAYS, entry.data.get(CONF_WPLAN_DAYS, DEFAULT_WPLAN_DAYS)))
        self.show_sub_text: bool = bool(entry.options.get(CONF_SHOW_SUB_TEXT, entry.data.get(CONF_SHOW_SUB_TEXT, True)))

        update_minutes = int(entry.options.get(CONF_UPDATE_MINUTES, DEFAULT_UPDATE_MINUTES))

        self.api = Stundenplan24Api(hass, self.username, self.password)

        # von number.py steuerbar (0=aktuelle Woche, 1=nächste, -1=letzte)
        self.week_offset: int = 0

        # Indiware (wplan/wdatenk) Cache pro Schulwoche
        self._indiware_basis_cache: Optional[dict] = None
        self._indiware_week_cache: Dict[int, Dict[str, Any]] = {}

        super().__init__(
            hass,
            logger=_LOGGER,
            name=f"stundenplan24_week_{self.target}",
            update_interval=timedelta(minutes=update_minutes),
        )

    # -------- Fetchers --------
    async def _fetch_mobil_plan_lessons(self, day_dt: datetime) -> Tuple[List[Tuple[int, str, str, str, str, str]], str]:
        """Basis: mobil PlanKlYYYYMMDD.xml. Returns (lessons, stand_ts)."""
        try:
            url = self.api.url_mobil_plan_kl_day(self.school_id, day_dt)
            xml_text = await self.api.fetch_text(
                url,
                referer=f"https://www.stundenplan24.de/{self.school_id}/mobil/",
                xhr=False,
            )
        except Exception as err:
            _LOGGER.debug("mobil Plan fetch failed %s: %s", ymd(day_dt), err)
            return [], ""

        if not xml_text:
            return [], ""

        stand = _extract_stand_from_xml(xml_text)

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
                return last, stand
        return last, stand

    async def _fetch_vplan_overlay_lessons(self, day_dt: datetime) -> Tuple[List[Tuple[int, str, str, str, str, str]], str, bool]:
        """Overlay: vplan/vdaten VplanKlYYYYMMDD.xml.

        Returns (lessons, stand_ts, vplan_day_available).
        The availability flag indicates that a day-specific VPlan XML exists, even
        if the selected class itself has no changed lessons on that day.
        """
        try:
            xml_text = await self.api.fetch_vplan_kl_day_xml(self.school_id, day_dt)
        except Exception as err:
            _LOGGER.debug("vplan fetch failed %s: %s", ymd(day_dt), err)
            return [], "", False

        if not xml_text:
            return [], "", False

        stand = _extract_stand_from_xml(xml_text)
        vplan_day_available = "<" in xml_text and "xml" in xml_text.lower()

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
                return last, stand, vplan_day_available
        return last, stand, vplan_day_available

    async def _fetch_wplan_info(self, day_dt: datetime) -> Dict[Tuple[int, int], str]:
        """Optional: mobil WPlanKlYYYYMMDD.xml als Zusatzinfos."""
        try:
            xml_text = await self.api.fetch_wplan_day_xml(self.school_id, day_dt)
        except Exception:
            return {}

        if not xml_text:
            return {}

        for tv in target_variants(self.target):
            info_map = parse_wplan_xml(xml_text, target_class=tv)
            if info_map:
                return info_map
        return {}

    
    # -------- Indiware Wochenplan Online (wplan/wdatenk) --------
    async def _fetch_indiware_basis(self) -> Optional[dict]:
        """Fetch + parse SPlanKl_Basis.xml. Returns dict with keys: ba_sw_von, ba_sw_bis, weeks(list)."""
        if self._indiware_basis_cache is not None:
            return self._indiware_basis_cache
        try:
            url = _url_indiware_basis(self.school_id)
            xml_text = await self.api.fetch_text(
                url,
                referer=f"https://www.stundenplan24.de/{self.school_id}/wplan/plan.html",
                xhr=True,
            )
        except Exception as err:
            _LOGGER.debug("Indiware basis fetch failed: %s", err)
            self._indiware_basis_cache = None
            return None

        if not xml_text or "<splan" not in xml_text:
            self._indiware_basis_cache = None
            return None

        try:
            root = ET.fromstring(xml_text)
            basis = root.find("Basisdaten")
            ba_sw_von = int(basis.findtext("BaSwVon", "0")) if basis is not None else 0
            ba_sw_bis = int(basis.findtext("BaSwBis", "0")) if basis is not None else 0

            weeks = []
            sws = root.find("Schulwochen")
            if sws is not None:
                for sw_el in sws.findall("Sw"):
                    sw_num = int((sw_el.text or "0").strip() or 0)
                    sw_von = sw_el.attrib.get("SwDatumVon", "")
                    sw_bis = sw_el.attrib.get("SwDatumBis", "")
                    weeks.append((sw_num, sw_von, sw_bis))
            out = {"ba_sw_von": ba_sw_von, "ba_sw_bis": ba_sw_bis, "weeks": weeks}
            self._indiware_basis_cache = out
            return out
        except Exception as err:
            _LOGGER.debug("Indiware basis parse failed: %s", err)
            self._indiware_basis_cache = None
            return None

    def _indiware_sw_for_date(self, basis: dict, day_dt: datetime) -> Optional[int]:
        for (sw_num, sw_von, sw_bis) in basis.get("weeks", []):
            if _indiware_date_in_range(day_dt, sw_von, sw_bis):
                return int(sw_num)
        return None

    async def _fetch_indiware_sw_xml(self, sw: int) -> Optional[str]:
        url = _url_indiware_sw(self.school_id, sw)
        try:
            return await self.api.fetch_text(
                url,
                referer=f"https://www.stundenplan24.de/{self.school_id}/wplan/plan.html",
                xhr=True,
            )
        except Exception as err:
            # bubble up 404 etc for debug, caller handles
            raise err

    def _parse_splankl_sw_for_target(
        self, xml_text: str
    ) -> Tuple[Dict[int, List[Tuple[int, str, str, str, str, str]]], str]:
        """Parse SPlanKl_SwXX.xml for target class. Returns (day_num->lessons, stand_ts)."""
        day_map: Dict[int, List[Tuple[int, str, str, str, str, str]]] = {1: [], 2: [], 3: [], 4: [], 5: []}
        stand = ""
        root = ET.fromstring(xml_text)
        stand = (root.findtext("Kopf/zeitstempel", "") or "").strip()

        # locate class node by Kurz
        target_set = set(target_variants(self.target))
        kl_node = None
        klassen = root.find("Klassen")
        if klassen is not None:
            for kl in klassen.findall("Kl"):
                kurz = (kl.findtext("Kurz", "") or "").strip()
                if kurz in target_set:
                    kl_node = kl
                    break
        if kl_node is None:
            return day_map, stand

        # times per hour
        times: Dict[int, Tuple[str, str]] = {}
        stunden = kl_node.find("Stunden")
        if stunden is not None:
            for st in stunden.findall("St"):
                try:
                    h = int((st.text or "0").strip() or 0)
                except Exception:
                    continue
                z1 = (st.attrib.get("StZeit", "") or "").strip()
                z2 = (st.attrib.get("StZeitBis", "") or "").strip()
                if h > 0:
                    times[h] = (z1, z2)

        pl = kl_node.find("Pl")
        if pl is None:
            return day_map, stand

        for std in pl.findall("Std"):
            try:
                day_num = int((std.findtext("PlTg", "0") or "0").strip() or 0)
                hour = int((std.findtext("PlSt", "0") or "0").strip() or 0)
            except Exception:
                continue
            if day_num < 1 or day_num > 5 or hour <= 0:
                continue

            fach = (std.findtext("PlFa", "") or "").strip()
            lehrer = (std.findtext("PlLe", "") or "").strip()
            raum = (std.findtext("PlRa", "") or "").strip()

            start, end = times.get(hour, ("", ""))
            day_map[day_num].append((hour, fach, lehrer, raum, start, end))

        return day_map, stand

    async def _ensure_indiware_week(self, monday_dt: datetime) -> Optional[Dict[str, Any]]:
        """Ensure Indiware week cache for school week corresponding to monday_dt (calendar monday)."""
        basis = await self._fetch_indiware_basis()
        if not basis:
            return None

        target_sw = self._indiware_sw_for_date(basis, monday_dt)
        if not target_sw:
            return None

        if target_sw in self._indiware_week_cache:
            return self._indiware_week_cache[target_sw]

        # fetch sw file; if missing, copy from nearest earlier available week within basis range
        ba_von = int(basis.get("ba_sw_von", 0) or 0)
        sw_to_try = target_sw
        xml_text = None
        used_sw = None
        last_err = ""
        for sw in range(sw_to_try, max(ba_von, 1) - 1, -1):
            try:
                xml_text = await self._fetch_indiware_sw_xml(sw)
                if xml_text and "<splan" in xml_text:
                    used_sw = sw
                    break
            except Exception as err:
                last_err = str(err)
                # try earlier
                continue

        if not xml_text or used_sw is None:
            self._indiware_week_cache[target_sw] = {"ok": False, "err": last_err, "target_sw": target_sw}
            return self._indiware_week_cache[target_sw]

        try:
            day_map, stand = self._parse_splankl_sw_for_target(xml_text)
            out = {
                "ok": True,
                "target_sw": target_sw,
                "used_sw": used_sw,
                "copied": used_sw != target_sw,
                "stand": stand,
                "day_map": day_map,
            }
            self._indiware_week_cache[target_sw] = out
            return out
        except Exception as err:
            self._indiware_week_cache[target_sw] = {"ok": False, "err": str(err), "target_sw": target_sw}
            return self._indiware_week_cache[target_sw]

    async def _fetch_day_bundle(self, week_monday: datetime, day_dt: datetime, use_current_week_mode: bool) -> Tuple[List[Tuple[int, str, str, str, str, str]], List[Tuple[int, str, str, str, str, str]], str, bool]:
        """Fetch base+overlay for a specific day.

        use_current_week_mode=True keeps the existing behavior for the actively
        selected week. For probed adjacent weeks we always prefer Indiware week
        base data when available.
        """
        if not use_current_week_mode:
            indi = await self._ensure_indiware_week(week_monday)
            if indi and indi.get("ok") and isinstance(indi.get("day_map"), dict):
                day_num = day_dt.weekday() + 1
                base_lessons = list(indi["day_map"].get(day_num, []))
                base_stand = indi.get("stand", "") or ""
                overlay_lessons, overlay_stand, overlay_available = await self._fetch_vplan_overlay_lessons(day_dt)
                stand = overlay_stand or (base_stand if overlay_available else "")
                return base_lessons, overlay_lessons, stand, overlay_available

        if int(self.week_offset) != 0 and use_current_week_mode:
            indi = await self._ensure_indiware_week(week_monday)
            if indi and indi.get("ok") and isinstance(indi.get("day_map"), dict):
                day_num = day_dt.weekday() + 1
                base_lessons = list(indi["day_map"].get(day_num, []))
                base_stand = indi.get("stand", "") or ""
                overlay_lessons, overlay_stand, overlay_available = await self._fetch_vplan_overlay_lessons(day_dt)
                stand = overlay_stand or (base_stand if overlay_available else "")
                return base_lessons, overlay_lessons, stand, overlay_available

        base_task = asyncio.create_task(self._fetch_mobil_plan_lessons(day_dt))
        ov_task = asyncio.create_task(self._fetch_vplan_overlay_lessons(day_dt))
        (base_lessons, base_stand), (overlay_lessons, overlay_stand, overlay_available) = await asyncio.gather(base_task, ov_task)
        stand = overlay_stand or base_stand or ""
        return base_lessons, overlay_lessons, stand, overlay_available

    def _build_exact_week_maps(
        self,
        day_dates: List[datetime],
        day_results: List[Tuple[List[Tuple[int, str, str, str, str, str]], List[Tuple[int, str, str, str, str, str]], str, bool]],
    ) -> Tuple[Dict[str, Dict[str, str]], Dict[str, str], Dict[str, bool]]:
        """Build date->time->cell maps for exact rolling rendering."""
        cells_by_date_time: Dict[str, Dict[str, str]] = {}
        updated_by_date: Dict[str, str] = {}
        available_by_date: Dict[str, bool] = {}

        for day_dt, (base_lessons, overlay_lessons, stand, overlay_available) in zip(day_dates, day_results):
            date_key = ymd(day_dt)
            updated_by_date[date_key] = _norm_ts(stand) if stand else ""
            available_by_date[date_key] = bool(overlay_available)

            by_hour: Dict[int, Dict[str, Any]] = {}
            time_minmax: Dict[int, Tuple[Optional[int], Optional[int]]] = {}

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

            for lessons, is_overlay in ((base_lessons, False), (overlay_lessons, True)):
                for (stunde, fach, lehrer, raum, start, end) in lessons:
                    if not stunde or stunde <= 0:
                        continue

                    row = by_hour.get(stunde)
                    if not row:
                        row = {"time": f"{stunde}.", "start": "", "end": "", "cell": ""}
                        by_hour[stunde] = row

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

                    lines: List[str] = []
                    lines.extend(_format_text(fach))
                    if self.show_room and raum:
                        lines.append(raum)
                    if self.show_teacher and lehrer:
                        lines.append(lehrer)

                    cell = "\n".join([l for l in lines if l]).strip()
                    if not cell:
                        continue

                    if is_overlay:
                        row["cell"] = _merge_cells((row["cell"] or "").strip(), cell)
                    else:
                        row["cell"] = _append_parallel((row["cell"] or "").strip(), cell)

            day_map: Dict[str, str] = {}
            for hour in sorted(by_hour.keys()):
                row = by_hour[hour]
                s, e = time_minmax.get(hour, (None, None))
                if s is not None:
                    row["start"] = to_hhmm(s)
                if e is not None:
                    row["end"] = to_hhmm(e)
                day_map[row["time"]] = (row["cell"] or "").strip()
            cells_by_date_time[date_key] = day_map

        return cells_by_date_time, updated_by_date, available_by_date

# -------- Update --------
    async def _async_update_data(self) -> Dict[str, Any]:
        try:
            today = datetime.now()
            monday = monday_of_week(today) + timedelta(weeks=int(self.week_offset))
            day_dates = weekdays_for_monday(monday)  # Mo..Fr

            by_hour: Dict[int, Dict[str, Any]] = {}
            time_minmax: Dict[int, Tuple[Optional[int], Optional[int]]] = {}

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

            # 1+2) BASIS + OVERLAY parallel pro Tag laden
            async def fetch_day(day_dt: datetime):
                return await self._fetch_day_bundle(monday, day_dt, use_current_week_mode=True)
                """
                # Basis je nach Modus:
                # - week_offset==0: mobil PlanKlYYYYMMDD.xml
                # - week_offset!=0: Indiware Wochenplan (SPlanKl_SwXX.xml) wenn verfügbar; sonst mobil PlanKl
                if int(self.week_offset) != 0:
                    indi = await self._ensure_indiware_week(monday)
                    if indi and indi.get("ok") and isinstance(indi.get("day_map"), dict):
                        day_num = (day_dt.weekday() + 1)  # Mo=1..Fr=5
                        base_lessons = list(indi["day_map"].get(day_num, []))
                        base_stand = indi.get("stand", "") or ""
                        ov_task = asyncio.create_task(self._fetch_vplan_overlay_lessons(day_dt))
                        (overlay_lessons, overlay_stand, overlay_available) = await ov_task
                        stand = overlay_stand or base_stand or ""
                        return base_lessons, overlay_lessons, stand, overlay_available
                base_task = asyncio.create_task(self._fetch_mobil_plan_lessons(day_dt))
                ov_task = asyncio.create_task(self._fetch_vplan_overlay_lessons(day_dt))
                (base_lessons, base_stand), (overlay_lessons, overlay_stand, overlay_available) = await asyncio.gather(base_task, ov_task)
                # Prefer overlay timestamp if present (typischerweise der tagesaktuelle Stand)
                stand = overlay_stand or base_stand or ""
                return base_lessons, overlay_lessons, stand, overlay_available

                """
            day_results = await asyncio.gather(*(fetch_day(d) for d in day_dates))

            # --- Updated/Stand timestamps (best-effort, per day) ---
            updated_days: List[str] = [_norm_ts(r[2]) if (len(r) > 2 and r[2]) else "" for r in day_results]
            updated_raw: str = next((u for u in updated_days if u), "")
            updated_error: str = "" if updated_raw else "no updated timestamp found in day XML (PlanKl/VplanKl)"
            vplan_missing_days: List[bool] = [not bool(r[3]) for r in day_results]
            vplan_available_by_date: Dict[str, bool] = {
                ymd(day_dt): bool(result[3]) for day_dt, result in zip(day_dates, day_results)
            }
            exact_cells_by_date_time, exact_updated_by_date, exact_available_by_date = self._build_exact_week_maps(
                day_dates,
                day_results,
            )

            for week_delta in (-2, -1, 1, 2):
                probe_monday = monday + timedelta(weeks=week_delta)
                probe_dates = weekdays_for_monday(probe_monday)
                probe_results = await asyncio.gather(
                    *(self._fetch_day_bundle(probe_monday, d, use_current_week_mode=False) for d in probe_dates)
                )
                probe_cells, probe_updated, probe_available = self._build_exact_week_maps(probe_dates, probe_results)
                exact_cells_by_date_time.update(probe_cells)
                exact_updated_by_date.update(probe_updated)
                exact_available_by_date.update(probe_available)
                vplan_available_by_date.update(probe_available)

            base_any = False
            overlay_any = False

            for col_idx, (base_lessons, overlay_lessons, _stand, _overlay_available) in enumerate(day_results):
                if base_lessons:
                    base_any = True
                if overlay_lessons:
                    overlay_any = True

                # ---- BASIS anwenden ----
                for (stunde, fach, lehrer, raum, start, end) in base_lessons:
                    if not stunde or stunde <= 0:
                        continue

                    row = by_hour.get(stunde)
                    if not row:
                        row = {"time": f"{stunde}.", "start": "", "end": "", "cells": ["", "", "", "", ""]}
                        by_hour[stunde] = row

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

                    lines: List[str] = []
                    lines.extend(_format_text(fach))
                    if self.show_room and raum:
                        lines.append(raum)
                    if self.show_teacher and lehrer:
                        lines.append(lehrer)

                    cell = "\n".join([l for l in lines if l]).strip()
                    if cell:
                        row["cells"][col_idx] = _append_parallel(row["cells"][col_idx] or "", cell)

                # ---- OVERLAY anwenden ----
                for (stunde, fach, lehrer, raum, start, end) in overlay_lessons:
                    if not stunde or stunde <= 0:
                        continue

                    row = by_hour.get(stunde)
                    if not row:
                        row = {"time": f"{stunde}.", "start": "", "end": "", "cells": ["", "", "", "", ""]}
                        by_hour[stunde] = row

                    smin = to_min(start)
                    emin = to_min(end)
                    cur_s, cur_e = time_minmax.get(stunde, (None, None))
                    if cur_s is None and smin is not None:
                        cur_s = smin
                    if cur_e is None and emin is not None:
                        cur_e = emin
                    time_minmax[stunde] = (cur_s, cur_e)

                    fach = (fach or "").strip()
                    lehrer = (lehrer or "").strip()
                    raum = (raum or "").strip()

                    lines = []
                    lines.extend(_format_text(fach))
                    if self.show_room and raum:
                        lines.append(raum)
                    if self.show_teacher and lehrer:
                        lines.append(lehrer)

                    overlay_cell = "\n".join([l for l in lines if l]).strip()
                    if not overlay_cell:
                        continue

                    base_cell = (row["cells"][col_idx] or "").strip()
                    row["cells"][col_idx] = _merge_cells(base_cell, overlay_cell)

            # 3) Optional: WPlan-Infos (Zusatztext)
            if self.wplan_enabled and self.show_sub_text:
                # Hinweis: wplan_days ist aktuell UI/Option; hier wird weiterhin nur Mo..Fr der gewählten Woche enriched.
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
                        row["cells"][col_idx] = _merge_cells(base_cell, "\n".join(info_lines))

            # Zeiten setzen
            for h, row in by_hour.items():
                s, e = time_minmax.get(h, (None, None))
                if s is not None:
                    row["start"] = to_hhmm(s)
                if e is not None:
                    row["end"] = to_hhmm(e)

            hours = sorted(by_hour.keys())
            rows = [by_hour[h] for h in hours]
            for row in rows:
                row["cells"] = [c.strip() if c and c.strip() else "" for c in row["cells"]]

            # Ferien / keine Daten in dieser Woche
            if not base_any and not overlay_any:
                # Fallback: Wenn noch keine PlanKl/VplanKl-Daten veröffentlicht sind,
                # aber der Wochenplan (wplan/plan.html) bereits Inhalte hat, nutze diesen als Basis.
                if self.wplan_enabled:
                    try:
                        html_text = await self.api.fetch_wplan_html(self.school_id)
                        wrows = parse_wplan_html_to_rows(html_text)
                        if wrows:
                            day_labels = ["Mo", "Di", "Mi", "Do", "Fr"]
                            rows_table = []
                            for r in wrows:
                                cells = r.get("cells") or ["", "", "", "", ""]
                                while len(cells) < 5:
                                    cells.append("")
                                row_tab = {"time": r.get("time",""), "start": r.get("start",""), "end": r.get("end","")}
                                for di, dl in enumerate(day_labels):
                                    row_tab[dl] = cells[di] if di < len(cells) else ""
                                rows_table.append(row_tab)
                            meta = {
                                "school_id": self.school_id,
                                "class": self.target,
                                "week_start": ymd(monday),
                                "days": [ymd(d) for d in day_dates],
                                "updated_days": updated_days,
                                "updated_raw": updated_raw,
                                "updated_error": updated_error,
                                "vplan_missing_days": vplan_missing_days,
                                "vplan_available_by_date": vplan_available_by_date,
                                "exact_cells_by_date_time": exact_cells_by_date_time,
                                "exact_updated_by_date": exact_updated_by_date,
                                "show_room": self.show_room,
                                "show_teacher": self.show_teacher,
                                "wplan_enabled": self.wplan_enabled,
                                "wplan_days": self.wplan_days,
                                "source": "fallback: wplan/plan.html (Wochenplan HTML) – solange PlanKl/VplanKl leer ist",
                                "wplan_fallback_used": True,
                                "no_plan": False,
                                "reason": "",
                                "week_offset": int(self.week_offset),
                            }
                            return {"rows": wrows, "rows_table": rows_table, "meta": meta}
                    except Exception as err:
                        _LOGGER.debug("WPlan HTML fallback failed: %s", err)
                return {
                    "rows": [],
                    "rows_table": [],
                    "meta": {
                        "school_id": self.school_id,
                        "class": self.target,
                        "week_start": ymd(monday),
                        "days": [ymd(d) for d in day_dates],
                        "updated_days": updated_days,
                        "updated_raw": updated_raw,
                        "updated_error": updated_error,
                        "vplan_missing_days": vplan_missing_days,
                        "vplan_available_by_date": vplan_available_by_date,
                        "exact_cells_by_date_time": exact_cells_by_date_time,
                        "exact_updated_by_date": exact_updated_by_date,
                        "show_room": self.show_room,
                        "show_teacher": self.show_teacher,
                        "wplan_enabled": self.wplan_enabled,
                        "wplan_days": self.wplan_days,
                        "source": "mobil PlanKl (Basis) + vplan/vdaten VplanKl (Overlay) + optional mobil WPlanKl",
                        "no_plan": True,
                        "reason": "Keine Daten (Ferien / nichts veröffentlicht)",
                        "week_offset": int(self.week_offset),
                    },
                }

            # rows_table (Mo/Di/...) für Karten, die keine `cells[]` lesen
            day_labels = ["Mo", "Di", "Mi", "Do", "Fr"]
            rows_table: List[Dict[str, Any]] = []
            for r in rows:
                cells = r.get("cells") or ["", "", "", "", ""]
                while len(cells) < 5:
                    cells.append("")
                d: Dict[str, Any] = {
                    "time": r.get("time", ""),
                    "start": r.get("start", ""),
                    "end": r.get("end", ""),
                }
                for i, lab in enumerate(day_labels):
                    d[lab] = (cells[i] or "").strip()
                rows_table.append(d)

            return {
                "rows": rows,
                "rows_table": rows_table,
                "meta": {
                    "school_id": self.school_id,
                    "class": self.target,
                    "week_start": ymd(monday),
                    "days": [ymd(d) for d in day_dates],
                    "updated_days": updated_days,
                    "updated_raw": updated_raw,
                    "updated_error": updated_error,
                    "vplan_missing_days": vplan_missing_days,
                    "vplan_available_by_date": vplan_available_by_date,
                    "exact_cells_by_date_time": exact_cells_by_date_time,
                    "exact_updated_by_date": exact_updated_by_date,
                    "show_room": self.show_room,
                    "show_teacher": self.show_teacher,
                    "wplan_enabled": self.wplan_enabled,
                    "wplan_days": self.wplan_days,
                    "source": "mobil PlanKl (Basis) + vplan/vdaten VplanKl (Overlay) + optional mobil WPlanKl",
                    "no_plan": False,
                    "week_offset": int(self.week_offset),
                },
            }

        except Exception as err:
            raise UpdateFailed(str(err)) from err
