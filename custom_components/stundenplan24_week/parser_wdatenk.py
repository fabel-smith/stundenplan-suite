from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple
import xml.etree.ElementTree as ET


# Home Assistant Card erwartet days typischerweise Mo..Fr
DAYS = ["Mo", "Di", "Mi", "Do", "Fr"]
DAY_NUM = {"Mo": 1, "Di": 2, "Mi": 3, "Do": 4, "Fr": 5, "Sa": 6, "So": 7}


@dataclass
class WeekInfo:
    sw: str
    von: str  # dd.mm.yyyy
    bis: str  # dd.mm.yyyy
    wo: Optional[str] = None  # "A"/"B"/None


def _text(node: Optional[ET.Element]) -> str:
    return (node.text or "").strip() if node is not None else ""


def _parse_de_date(s: str) -> Optional[date]:
    s = (s or "").strip()
    # akzeptiert: "02.02.2026" oder "02. 02. 2026"
    s = s.replace(" ", "")
    try:
        return datetime.strptime(s, "%d.%m.%Y").date()
    except Exception:
        return None


def parse_basis(basis_xml: str) -> Tuple[List[str], List[WeekInfo]]:
    """
    Liest aus SPlanKl_Basis.xml:
    - Klassen (Kurz)
    - Schulwochen (Sw + Von/Bis + optional SwWo)
    """
    root = ET.fromstring(basis_xml)

    classes: List[str] = []
    for n in root.findall(".//Klassen/Kl/Kurz"):
        v = _text(n)
        if v:
            classes.append(v)

    weeks: List[WeekInfo] = []
    for sw in root.findall(".//Schulwochen/Sw"):
        nr = _text(sw)
        von = (sw.attrib.get("SwDatumVon") or "").strip()
        bis = (sw.attrib.get("SwDatumBis") or "").strip()
        wo = (sw.attrib.get("SwWo") or "").strip().upper() or None
        if wo not in ("A", "B"):
            wo = None
        if nr and von and bis:
            weeks.append(WeekInfo(sw=nr, von=von, bis=bis, wo=wo))

    return classes, weeks


def find_school_week(weeks: List[WeekInfo], today: Optional[date] = None) -> Optional[WeekInfo]:
    today = today or date.today()
    for w in weeks:
        d1 = _parse_de_date(w.von)
        d2 = _parse_de_date(w.bis)
        if not d1 or not d2:
            continue
        if d1 <= today <= d2:
            return w
    return None


def _norm_target(target: str) -> str:
    return (target or "").strip().lower()


def match_plkl(plkl: str, target: str) -> bool:
    """
    Wochenplan hat i.d.R. PlKl sauber (z.B. "05a", "5a", "05A").
    Wir matchen strikt (case-insensitive, trim).
    """
    return _norm_target(plkl) == _norm_target(target)


def parse_weekplan_splan(xml_text: str, target_class: str, show_room: bool, show_teacher: bool) -> List[dict]:
    """
    Liest SPlanKl_SwXX.xml (wdatenk) und gibt rows im Card-Format:
    [
      { "time":"1.", "start":None, "end":None, "cells":[...Mo..Fr...] },
      ...
    ]
    Zeiten sind hier meist nicht enthalten -> Card kann über manuelle rows fallbacken.
    """
    root = ET.fromstring(xml_text)

    # Std-Knoten kommen oft unter <Pl><Std>...</Std></Pl> oder direkt <Std>
    std_nodes = root.findall(".//Std")
    lessons = []

    for std in std_nodes:
        day = int((_text(std.find("PlTg")) or "0").strip() or 0)   # 1..7
        hour = int((_text(std.find("PlSt")) or "0").strip() or 0)  # 1..n
        if day <= 0 or hour <= 0:
            continue

        plkl = _text(std.find("PlKl"))
        if plkl and not match_plkl(plkl, target_class):
            continue

        subject = _text(std.find("PlFa"))
        teacher = _text(std.find("PlLe"))
        room = _text(std.find("PlRa"))

        if not subject and not teacher and not room:
            continue

        extras = []
        if show_room and room:
            extras.append(room)
        if show_teacher and teacher:
            extras.append(teacher)

        cell = subject.strip()
        if extras and cell:
            cell = f"{cell} ({' · '.join(extras)})"
        elif not cell:
            # falls Fach leer ist, aber z.B. Raum/Lehrer da
            cell = " · ".join(extras)

        lessons.append((day, hour, cell))

    if not lessons:
        return []

    # Stunden & Tage sammeln
    hours = sorted({h for (_, h, _) in lessons})
    day_to_col = {1: 0, 2: 1, 3: 2, 4: 3, 5: 4}  # Mo..Fr

    # Aggregation: (hour, col) -> list[str]
    grid: Dict[Tuple[int, int], List[str]] = {}
    for day, hour, cell in lessons:
        if day not in day_to_col:
            continue
        col = day_to_col[day]
        grid.setdefault((hour, col), [])
        if cell and cell not in grid[(hour, col)]:
            grid[(hour, col)].append(cell)

    rows: List[dict] = []
    for h in hours:
        cells = []
        for col in range(len(DAYS)):
            parts = grid.get((h, col), [])
            cells.append(" / ".join(parts) if parts else "")
        rows.append(
            {
                "time": f"{h}.",
                "start": None,
                "end": None,
                "cells": cells,
            }
        )

    return rows
