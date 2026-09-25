from __future__ import annotations

import asyncio
import time
import datetime as _dt
from collections import OrderedDict
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
import math
import aiohttp

from homeassistant.helpers.aiohttp_client import async_get_clientsession

BASE = "https://www.stundenplan24.de"
HTTP_STATE_KEY = "stundenplan24_week_http"
CACHE_SECONDS = 30
CACHE_LIMIT = 128
REQUEST_SPACING = 0.5


class Stundenplan24RequestBlocked(Exception):
    """Stop all endpoint fallbacks when access or service availability fails."""


@dataclass
class _RequestGate:
    # Shared across entries: several children must not multiply concurrent traffic.
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    next_request: float = 0
    blocked_until: float = 0
    reason: str = ""
    rate_failures: int = 0


def retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        delay = float(value)
    except ValueError:
        try:
            stamp = parsedate_to_datetime(value)
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=_dt.timezone.utc)
            delay = stamp.timestamp() - time.time()
        except (ValueError, TypeError, OverflowError):
            return None
    return max(1.0, delay) if math.isfinite(delay) else None

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
        self._gate = hass.data.setdefault(HTTP_STATE_KEY, _RequestGate())
        self._access_error: str | None = None
        self._cache: OrderedDict[tuple, tuple[float, str]] = OrderedDict()

    def raise_if_blocked(self) -> None:
        if self._access_error:
            raise Stundenplan24RequestBlocked(self._access_error)
        remaining = self._gate.blocked_until - time.monotonic()
        if remaining > 0:
            raise Stundenplan24RequestBlocked(
                f"{self._gate.reason} Erneuter Abruf fruehestens in {math.ceil(remaining)} Sekunden."
            )

    def _cooldown(self, seconds: float, reason: str) -> None:
        self._gate.blocked_until = max(self._gate.blocked_until, time.monotonic() + seconds)
        self._gate.reason = reason

    def _base_headers(self) -> dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
            # Revalidate upstream caches without generating a new URL for every request.
            "Cache-Control": "no-cache",
        }

    async def fetch_text(self, url: str, *, referer: str | None = None, xhr: bool = False) -> str:
        session = async_get_clientsession(self._hass)
        headers = self._base_headers()
        if referer:
            headers["Referer"] = referer
        if xhr:
            headers["X-Requested-With"] = "XMLHttpRequest"

        key = (url, referer, xhr)
        async with self._gate.lock:
            self.raise_if_blocked()
            cached = self._cache.get(key)
            if cached and cached[0] > time.monotonic():
                self._cache.move_to_end(key)
                return cached[1]
            for attempt in range(2):
                await asyncio.sleep(max(0, self._gate.next_request - time.monotonic()))
                self.raise_if_blocked()
                try:
                    async with session.get(url, auth=self._auth, timeout=self._timeout, headers=headers) as resp:
                        if resp.status in (401, 403):
                            self._access_error = (
                                f"Stundenplan24 verweigert den Zugriff (HTTP {resp.status}). "
                                "Zugangsdaten und Berechtigung pruefen; danach Integration neu laden."
                            )
                            self.raise_if_blocked()
                        if resp.status in (429, 503):
                            self._gate.rate_failures += 1
                            fallback = min(3600, 60 * 2 ** min(self._gate.rate_failures - 1, 6))
                            self._cooldown(
                                retry_after_seconds(resp.headers.get("Retry-After")) or fallback,
                                f"Stundenplan24 begrenzt Abrufe oder ist voruebergehend nicht verfuegbar (HTTP {resp.status}).",
                            )
                            self.raise_if_blocked()
                        resp.raise_for_status()
                        result = await resp.text()
                        self._gate.rate_failures = 0
                        self._cache[key] = (time.monotonic() + CACHE_SECONDS, result)
                        self._cache.move_to_end(key)
                        while len(self._cache) > CACHE_LIMIT:
                            self._cache.popitem(last=False)
                        return result
                except aiohttp.ClientResponseError as err:
                    # Missing optional files may use another endpoint, but are not retried.
                    if err.status < 500:
                        raise
                    if attempt:
                        self._cooldown(60, "Stundenplan24 meldet wiederholt einen Serverfehler.")
                        self.raise_if_blocked()
                except (aiohttp.ClientError, asyncio.TimeoutError):
                    if attempt:
                        self._cooldown(60, "Stundenplan24 ist derzeit nicht erreichbar.")
                        self.raise_if_blocked()
                finally:
                    self._gate.next_request = time.monotonic() + REQUEST_SPACING
                await asyncio.sleep(2)
        raise RuntimeError("Fetch fehlgeschlagen")

    # ----------------------------
    # URL builder helpers
    # ----------------------------
    def url_vplan_kl_xml(self, school_id: str) -> str:
        return f"{BASE}/{school_id}/vplan/vdaten/VplanKl.xml"

    def url_vplan_kl_day_xml(self, school_id: str, day) -> str:
        return f"{BASE}/{school_id}/vplan/vdaten/VplanKl{ymd(day)}.xml"

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
        except Stundenplan24RequestBlocked:
            raise
        except Exception:
            return await self.fetch_mobil_wplan_kl_day_xml(school_id, day)

    async def fetch_wplan_html(self, school_id: str, day=None) -> str:
        # Some schools require the Wochenplan page as the referer.
        return await self.fetch_text(self.url_wplan_html(school_id, day), referer=self.url_wplan_root(school_id), xhr=False)
