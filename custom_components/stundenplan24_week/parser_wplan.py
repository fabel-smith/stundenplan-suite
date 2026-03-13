from __future__ import annotations

import html
from typing import Dict, List, Tuple
import xml.etree.ElementTree as ET

RED_MARKER = "[[sp-red]]"


def _txt(el) -> str:
    if el is None:
        return ""
    raw = "".join(el.itertext()) if hasattr(el, "itertext") else (el.text or "")
    raw = html.unescape(raw or "").replace("\xa0", " ").strip()
    if raw.lower() == "&nbsp;":
        return ""
    return raw


def _mark_if_changed(value: str, changed: str) -> str:
    v = (value or "").strip()
    if not v:
        return v
    if (changed or "").strip():
        return f"{RED_MARKER}{v}"
    return v


def parse_wplan_xml(xml_text: str, target_class: str) -> Dict[Tuple[int, int], str]:
    """
    Mobil WPlanKlYYYYMMDD.xml:
    Return dict[(day_num, hour)] = info_text
    day_num: 1..5 (Mo..Fr)
    """

    out: Dict[Tuple[int, int], str] = {}
    if not xml_text:
        return out

    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return out

    tclass = (target_class or "").strip()
    if not tclass:
        return out

    # Sehr robust: suche Einträge, die Kurz/Klasse enthalten
    for node in root.findall(".//*"):
        kurz = _txt(node.find("Kurz")) or _txt(node.find("klasse")) or _txt(node.find("Klasse"))
        if kurz != tclass:
            continue

        # Tag/TagNr und Stunde
        day_txt = _txt(node.find("Tag")) or _txt(node.find("Day")) or _txt(node.find("T"))
        hour_txt = _txt(node.find("St")) or _txt(node.find("Std")) or _txt(node.find("Stunde"))

        try:
            day_num = int(day_txt)
            hour = int(hour_txt)
        except Exception:
            continue

        info = _txt(node.find("If")) or _txt(node.find("Info")) or _txt(node.find("Text"))
        if info:
            out[(day_num, hour)] = info

    return out


def parse_wplan_day_xml_lessons(
    xml_text: str,
    target_class: str,
    show_room: bool = True,
    show_teacher: bool = False,
) -> List[Tuple[int, str, str, str, str, str]]:
    """
    Parse wplan/wdatenk/WPlanKl_YYYYMMDD.xml for one class.

    Returns tuples compatible with parse_plan_klassen_xml:
      (stunde, fach_plus_info, lehrer, raum, start, end)

    These day files carry the future-day changes that the Wochenplan Online UI
    overlays onto the base SPlan week.
    """
    out: List[Tuple[int, str, str, str, str, str]] = []
    if not xml_text:
        return out

    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return out

    tclass = (target_class or "").strip()
    if not tclass:
        return out

    for kl in root.findall(".//Kl"):
        kurz = _txt(kl.find("Kurz"))
        if kurz != tclass:
            continue

        for std in kl.findall(".//Std"):
            st_txt = _txt(std.find(".//St")) or _txt(std.find(".//Std")) or _txt(std.find(".//Stunde"))
            try:
                stunde = int(st_txt)
            except Exception:
                continue

            fa_node = std.find(".//Fa")
            le_node = std.find(".//Le")
            ra_node = std.find(".//Ra")

            fach = _txt(fa_node) or _txt(std.find(".//Fach"))
            lehrer = _txt(le_node) or _txt(std.find(".//Lehrer"))
            raum = _txt(ra_node) or _txt(std.find(".//Raum"))
            info = _txt(std.find(".//If")) or _txt(std.find(".//Info")) or _txt(std.find(".//Text"))
            aend_fach = (fa_node.attrib.get("FaAe", "") if fa_node is not None else "").strip()
            aend_lehrer = (le_node.attrib.get("LeAe", "") if le_node is not None else "").strip()
            aend_raum = (ra_node.attrib.get("RaAe", "") if ra_node is not None else "").strip()

            fach = (fach or "").strip()
            lehrer = (lehrer or "").strip()
            raum = (raum or "").strip()
            info = (info or "").strip()

            if fach in {"&nbsp;", "\xa0"}:
                fach = ""
            if lehrer in {"&nbsp;", "\xa0"}:
                lehrer = ""
            if raum in {"&nbsp;", "\xa0"}:
                raum = ""

            if not fach and info:
                fach = info
                info = ""

            if not fach and not lehrer and not raum and not info:
                continue

            # Indiware shows a visible placeholder when the subject itself changed
            # to "empty", e.g. canceled first lessons in future weeks.
            if not fach and aend_fach == "FaGeaendert":
                fach = "---"

            fach = _mark_if_changed(fach, aend_fach)
            lehrer = _mark_if_changed(lehrer, aend_lehrer)
            raum = _mark_if_changed(raum, aend_raum)

            fach_plus = fach
            if info and info not in fach_plus:
                fach_plus = f"{fach_plus}\n{info}".strip()

            out.append((stunde, fach_plus, lehrer, raum, "", ""))

    return out
