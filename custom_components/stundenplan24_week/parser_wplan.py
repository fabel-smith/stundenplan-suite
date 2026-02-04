from __future__ import annotations

from typing import Dict, List, Optional, Tuple
import xml.etree.ElementTree as ET


def _text(node: Optional[ET.Element]) -> str:
    return (node.text or "").strip() if node is not None else ""


def _norm_target(target: str) -> str:
    return (target or "").strip().lower()


def match_plkl(plkl: str, target: str) -> bool:
    return _norm_target(plkl) == _norm_target(target)


def _extract_info(std: ET.Element) -> str:
    """
    WPlanKlYYYYMMDD.xml enthält je nach System unterschiedliche Felder.
    Wir versuchen robust die "Info"/Bemerkung/Vertretungstexte zu finden.

    Strategie:
    1) bekannte Tag-Namen bevorzugen (häufige Kandidaten)
    2) fallback: alle Textfelder einsammeln, die nicht Basisfelder sind
    """
    preferred_tags = [
        "PlTx", "PlTxt", "PlText", "PlInfo", "PlBem", "PlBemerkung",
        "PlZu", "PlZusatz", "PlVe", "PlVertretung", "PlHinweis",
        "PlNotiz", "PlKommentar",
    ]

    # 1) Prefered
    parts: List[str] = []
    for tag in preferred_tags:
        v = _text(std.find(tag))
        if v:
            parts.append(v)

    if parts:
        return " | ".join(dict.fromkeys(parts)).strip()

    # 2) Fallback: alles außer Basisfeldern
    base = {"PlTg", "PlSt", "PlKl", "PlFa", "PlLe", "PlRa"}
    for child in list(std):
        if child.tag in base:
            continue
        v = _text(child)
        if v:
            parts.append(v)

    # Duplikate raus, Reihenfolge behalten
    uniq: List[str] = []
    seen = set()
    for p in parts:
        if p not in seen:
            uniq.append(p)
            seen.add(p)

    return " | ".join(uniq).strip()


def parse_wplan_xml(xml_text: str, target_class: str) -> Dict[Tuple[int, int], str]:
    """
    Gibt mapping (day:int 1..7, hour:int 1..n) -> info_text zurück.
    Filtert auf Klasse (PlKl).
    """
    root = ET.fromstring(xml_text)

    std_nodes = root.findall(".//Std")
    out: Dict[Tuple[int, int], str] = {}

    for std in std_nodes:
        day = int((_text(std.find("PlTg")) or "0") or 0)
        hour = int((_text(std.find("PlSt")) or "0") or 0)
        if day <= 0 or hour <= 0:
            continue

        plkl = _text(std.find("PlKl"))
        if plkl and not match_plkl(plkl, target_class):
            continue

        info = _extract_info(std)
        if not info:
            continue

        key = (day, hour)
        # falls mehrere Einträge pro Stunde: zusammenführen
        if key in out and info not in out[key]:
            out[key] = f"{out[key]} | {info}"
        else:
            out[key] = info

    return out
