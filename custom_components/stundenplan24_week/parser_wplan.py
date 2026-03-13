from __future__ import annotations

from typing import Dict, Tuple
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
