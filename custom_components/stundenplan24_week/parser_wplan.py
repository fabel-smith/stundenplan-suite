from __future__ import annotations

from typing import Dict, List, Tuple
import xml.etree.ElementTree as ET


def _txt(el) -> str:
    if el is None or el.text is None:
        return ""
    return el.text.strip()


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
            st_txt = _txt(std.find("St"))
            try:
                stunde = int(st_txt)
            except Exception:
                continue

            fach = _txt(std.find("Fa"))
            lehrer = _txt(std.find("Le"))
            raum = _txt(std.find("Ra"))
            info = _txt(std.find("If")) or _txt(std.find("Info")) or _txt(std.find("Text"))

            fach = (fach or "").strip()
            info = (info or "").strip()

            if not fach and info:
                fach = info
                info = ""

            if not fach and not lehrer and not raum and not info:
                continue

            fach_plus = fach
            if info and info not in fach_plus:
                fach_plus = f"{fach_plus}\n{info}".strip()

            out.append((stunde, fach_plus, lehrer, raum, "", ""))

    return out
