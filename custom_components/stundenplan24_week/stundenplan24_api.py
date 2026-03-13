from __future__ import annotations

import asyncio
import time
import datetime as _dt
import aiohttp

from homeassistant.helpers.aiohttp_client import async_get_clientsession

BASE = "https://www.stundenplan24.de"

def ymd(day) -> str:
    """Return YYYYMMDD for various day representations (date/datetime/str)."""
    if day is None:
        return ""
    if isinstance(day, (_dt.datetime, _dt.date)):
        return day.strftime("%Y%m%d")
    s = str(day).strip()
    # common ISO 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS' -> keep digits
    digits = "".join(ch for ch in s if ch.isdigit())
    if len(digits) >= 8:
        return digits[:8]
    return s

class Stundenplan24Api:
    """HTTP client for Stundenplan24 endpoints.

    Provides backwards-compatible methods expected by coordinator.py:
      - url_mobil_plan_kl_day
      - fetch_vplan_kl_day_xml
      - fetch_mobil_plan_kl_day_xml
      - fetch_mobil_wplan_kl_day_xml
      - fetch_wplan_html
    """

    def __init__(self, hass, username: str, password: str, timeout_s: int = 25) -> None:
        self._hass = hass
        self._auth = aiohttp.BasicAuth(username, password)
        self._timeout = aiohttp.ClientTimeout(total=timeout_s)

    def _base_headers(self) -> dict[str, str]:
        # Stundenplan24 blocks some requests unless they look like a browser.
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache",
        }

    async def fetch_text(self, url: str, *, referer: str | None = None, xhr: bool = False) -> str:
        session = async_get_clientsession(self._hass)
        headers = self._base_headers()
        if referer:
            headers["Referer"] = referer
        if xhr:
            headers["X-Requested-With"] = "XMLHttpRequest"

        last_err: Exception | None = None
        for _ in range(2):  # retry once
            try:
                async with session.get(
                    url,
                    auth=self._auth,
                    timeout=self._timeout,
                    headers=headers,
                ) as resp:
                    resp.raise_for_status()
                    return await resp.text()
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_err = e
        raise last_err or RuntimeError("Fetch fehlgeschlagen")

    # ----------------------------
    # URL builder helpers
    # ----------------------------
    def url_vplan_kl_xml(self, school_id: str) -> str:
        return f"{BASE}/{school_id}/vplan/vdaten/VplanKl.xml?_={int(time.time()*1000)}"

    def url_vplan_kl_day_xml(self, school_id: str, day) -> str:
        return f"{BASE}/{school_id}/vplan/vdaten/VplanKl{ymd(day)}.xml?_={int(time.time()*1000)}"

    def url_mobil_plan_kl_day(self, school_id: str, day) -> str:
        return f"{BASE}/{school_id}/mobil/mobdaten/PlanKl{ymd(day)}.xml"

    def url_mobil_wplan_kl_day(self, school_id: str, day) -> str:
        return f"{BASE}/{school_id}/mobil/mobdaten/WPlanKl{ymd(day)}.xml"

    def url_wplan_day_xml(self, school_id: str, day) -> str:
        return f"{BASE}/{school_id}/wplan/wdatenk/WPlanKl_{ymd(day)}.xml"

    def url_wplan_html(self, school_id: str, day=None) -> str:
        # plan.html without params usually shows only the current week.
        # Stundenplan24 supports selecting calendar week via a query param.
        if day:
            y = ymd(day)
            try:
                d = _dt.datetime.strptime(y, "%Y%m%d").date()
                year, week, _ = d.isocalendar()
                return f"{BASE}/{school_id}/wplan/plan.html?week={year}{week:02d}"
            except Exception:
                pass
        return f"{BASE}/{school_id}/wplan/plan.html"

    def url_vplan_root(self, school_id: str) -> str:
        return f"{BASE}/{school_id}/"

    def url_wplan_root(self, school_id: str) -> str:
        return f"{BASE}/{school_id}/wplan/"

    # ----------------------------
    # Fetch helpers expected by coordinator
    # ----------------------------
    async def fetch_vplan_kl_xml(self, school_id: str) -> str:
        return await self.fetch_text(self.url_vplan_kl_xml(school_id), referer=self.url_vplan_root(school_id), xhr=True)

    async def fetch_vplan_kl_day_xml(self, school_id: str, day) -> str:
        return await self.fetch_text(self.url_vplan_kl_day_xml(school_id, day), referer=self.url_vplan_root(school_id), xhr=True)

    async def fetch_mobil_plan_kl_day_xml(self, school_id: str, day) -> str:
        return await self.fetch_text(self.url_mobil_plan_kl_day(school_id, day), referer=self.url_vplan_root(school_id), xhr=False)

    async def fetch_mobil_wplan_kl_day_xml(self, school_id: str, day) -> str:
        return await self.fetch_text(self.url_mobil_wplan_kl_day(school_id, day), referer=self.url_vplan_root(school_id), xhr=False)

    async def fetch_wplan_day_xml(self, school_id: str, day) -> str:
        """Fetch Wochenplan Online day XML used by the browser week view."""
        try:
            return await self.fetch_text(self.url_wplan_day_xml(school_id, day), referer=self.url_wplan_root(school_id), xhr=False)
        except Exception:
            return await self.fetch_mobil_wplan_kl_day_xml(school_id, day)

    async def fetch_wplan_html(self, school_id: str, day=None) -> str:
        # Important: Referer must point to /wplan/ for some schools, plus browser-like UA.
        return await self.fetch_text(self.url_wplan_html(school_id, day), referer=self.url_wplan_root(school_id), xhr=False)
