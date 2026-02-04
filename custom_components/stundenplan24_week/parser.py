from __future__ import annotations

from typing import List, Tuple
import xml.etree.ElementTree as ET


def _txt(el) -> str:
    if el is None or el.text is None:
        return ""
    return el.text.strip()


def parse_plan_klassen_xml(
    xml_text: str,
    target_class: str,
    show_room: bool = True,
    show_teacher: bool = False,
) -> List[Tuple[int, str, str, str, str, str]]:
    """
    Returns list of tuples:
      (stunde:int, fach_plus_info:str, lehrer:str, raum:str, start:str, end:str)

    Wichtig:
    - Info aus <If> wird IMMER als zweite Zeile an "fach" angehängt (wenn vorhanden),
      damit wir es später sauber formatieren können (Zeilenumbrüche, Markierung etc.).
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

    kl_node = None
    for kl in root.findall(".//Klassen/Kl"):
        kurz = _txt(kl.find("Kurz"))
        if kurz == tclass:
            kl_node = kl
            break

    if kl_node is None:
        return out

    for std in kl_node.findall(".//Pl/Std"):
        st_txt = _txt(std.find("St"))
        try:
            stunde = int(st_txt)
        except Exception:
            continue

        start = _txt(std.find("Beginn"))
        end = _txt(std.find("Ende"))

        fach = _txt(std.find("Fa"))
        lehrer = _txt(std.find("Le"))
        raum = _txt(std.find("Ra"))
        info = _txt(std.find("If"))

        fach = (fach or "").strip()
        info = (info or "").strip()

        # Fach ggf. leer -> Info als Fach
        if not fach and info:
            fach = info
            info = ""

        # Wenn beides leer ist: ignorieren
        if not fach and not info:
            continue

        # Info immer als 2. Zeile anhängen (wenn vorhanden)
        fach_plus = fach
        if info and info not in fach_plus:
            fach_plus = f"{fach_plus}\n{info}".strip()

        out.append((stunde, fach_plus, lehrer, raum, start, end))

    return out
