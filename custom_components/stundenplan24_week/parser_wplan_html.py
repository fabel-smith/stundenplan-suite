from __future__ import annotations

import html as _html
import re
from typing import List, Dict, Any


_RE_TR = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
_RE_TD = re.compile(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", re.IGNORECASE | re.DOTALL)

def _cell_text(inner_html: str) -> str:
    """HTML-Zelleninhalt -> Text mit Zeilenumbrüchen."""
    s = inner_html or ""
    # br -> newline
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.IGNORECASE)
    # Entities
    s = _html.unescape(s)
    # Tags entfernen
    s = re.sub(r"<[^>]+>", "", s)
    # Whitespace normalisieren, aber newlines erhalten
    s = s.replace("\r", "")
    s = "\n".join([ln.strip() for ln in s.split("\n")])
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip()

def _parse_time_range(txt: str) -> tuple[str, str]:
    # findet z.B. "08:10" und "08:55" irgendwo im Text
    m = re.findall(r"\b(\d{1,2}:\d{2})\b", txt)
    if len(m) >= 2:
        # normalisiere auf 2-stellig
        def norm(t: str) -> str:
            hh, mm = t.split(":")
            return f"{int(hh):02d}:{mm}"
        return norm(m[0]), norm(m[1])
    return "", ""

def parse_wplan_html_to_rows(html_text: str) -> List[Dict[str, Any]]:
    """
    Extrahiert Wochenplan (Mo–Fr) aus Indiware Wochenplan HTML.

    Unterstützt Layouts mit:
    - 1 linker Spalte (Stunde+Zeit zusammen)
    - 2 linken Spalten (Stunde | Zeit)  -> häufig bei plan.html
    - ggf. zusätzliche Zwischen-Spalten, solange 5 Tages-Spalten (Mo–Fr) vorhanden sind.

    Ergebnisformat: rows=[{time,start,end,cells[5]}...]
    """
    if not html_text:
        return []

    rows: List[Dict[str, Any]] = []

    trs = _RE_TR.findall(html_text)
    for tr in trs:
        tds = _RE_TD.findall(tr)
        if len(tds) < 6:
            continue

        left0 = _cell_text(tds[0])
        left1 = _cell_text(tds[1]) if len(tds) > 1 else ""

        m_hour = re.search(r"\b(\d{1,2})\b", left0) or re.search(r"\b(\d{1,2})\b", left1)
        if not m_hour:
            continue
        hour = int(m_hour.group(1))
        if hour <= 0 or hour > 20:
            continue

        start_t, end_t = _parse_time_range(left1 or left0)

        # Tageszellen: meist ab Index 2 (Stunde|Zeit|Mo..Fr)
        day_cells_raw = None
        for ds in (2, 3, 1, 0):
            if len(tds) >= ds + 5:
                day_cells_raw = tds[ds:ds+5]
                break
        if day_cells_raw is None:
            day_cells_raw = tds[-5:]

        cells: List[str] = []
        for c in day_cells_raw[:5]:
            cells.append(_cell_text(c))

        time_label = str(hour)
        if start_t and end_t:
            time_label = f"{hour} {start_t}-{end_t}"

        rows.append({"time": time_label, "start": start_t, "end": end_t, "cells": cells})

    def _hour_key(r: Dict[str, Any]) -> int:
        mm = re.search(r"\b(\d{1,2})\b", str(r.get("time","")))
        return int(mm.group(1)) if mm else 999

    rows.sort(key=_hour_key)
    return rows
