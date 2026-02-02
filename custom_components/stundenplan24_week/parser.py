from __future__ import annotations

import re
from xml.etree import ElementTree as ET

DAYS = ["Mo", "Di", "Mi", "Do", "Fr"]
DAY_NUM = {"Mo": 1, "Di": 2, "Mi": 3, "Do": 4, "Fr": 5}


def _norm(s: str) -> str:
    return (s or "").replace("\u00a0", " ").strip()


def _text(node: ET.Element, *paths: str) -> str:
    for p in paths:
        el = node.find(p)
        if el is not None and el.text:
            t = _norm(el.text)
            if t:
                return t
    return ""


def _int(node: ET.Element, *paths: str) -> int:
    for p in paths:
        t = _text(node, p)
        if t.isdigit():
            return int(t)
    return 0


def match_class(plkl: str, target: str) -> bool:
    """
    Sehr strikt:
    - exact match: 05a
    - oder in Listen: 05a/05b, 05a,05b
    """
    if not plkl or not target:
        return False

    plkl = plkl.replace("\u00a0", " ").strip().lower()
    target = target.strip().lower()

    # exakt
    if plkl == target:
        return True

    # split an typischen Trennern
    parts = re.split(r"[,\s/;|]+", plkl)
    return target in parts



def parse_plan_klassen_xml(
    xml_text: str,
    target_class: str,
    show_room: bool,
    show_teacher: bool,
    days: list[str] = DAYS,
) -> list[dict]:
    """
    Erwartet PlanKlYYYYMMDD.xml (mobile) oder ähnliches.
    Ergebnis: rows im Card-Format:
      - Unterricht: {time, start, end, cells:[..]}
    """
    root = ET.fromstring(xml_text)

    # wir suchen Stunden/Einträge; je nach Export leicht unterschiedlich
    # häufig: <Std>...<St>1</St><Fa>DE</Fa><Le>MU</Le><Ra>139</Ra><Kl>05a</Kl>...
    std_nodes = root.findall(".//Std")
    if not std_nodes:
        return []

    # Sammeln: (day, hour) -> (fach, lehrer, raum, start, end)
    # Mobile XML ist oft tagesbezogen => day ist implizit; wir setzen es anhand des Date-DOW später
    # Für Wochenansicht machen wir erstmal: du rufst 5 Tage ab und mergst (kommt im Coordinator)
    out = {}  # hour -> placeholder, wird im Coordinator pro Tag befüllt

    # nur Stunden, die zur Zielklasse gehören
    lessons = []
    for std in std_nodes:
        st = _int(std, "St", "PlSt")
        if st <= 0:
            continue

        kl = _text(std, "Kl", "PlKl")
        if kl and target_class and not match_class(kl, target_class):
            continue

        fach = _text(std, "Fa", "PlFa")
        lehrer = _text(std, "Le", "PlLe")
        raum = _text(std, "Ra", "PlRa")

        start = _text(std, "Beginn", "Be", "Start", "PlBe")  # je nach XML
        end = _text(std, "Ende", "En", "End", "PlEn")

        lessons.append((st, fach, lehrer, raum, start, end))

    # wir geben die rohen Lessons zurück; Merging passiert im Coordinator
    # Format: list of tuples
    return lessons
