from __future__ import annotations

import asyncio
import aiohttp

from homeassistant.helpers.aiohttp_client import async_get_clientsession


class Stundenplan24Api:
    def __init__(self, hass, username: str, password: str, timeout_s: int = 20) -> None:
        self._hass = hass
        self._auth = aiohttp.BasicAuth(username, password)
        self._timeout = aiohttp.ClientTimeout(total=timeout_s)

    async def fetch_text(self, url: str) -> str:
        session = async_get_clientsession(self._hass)

        last_err: Exception | None = None
        for _ in range(2):  # 1 Retry
            try:
                async with session.get(
                    url,
                    auth=self._auth,
                    timeout=self._timeout,
                    headers={"Cache-Control": "no-cache"},
                ) as resp:
                    resp.raise_for_status()
                    return await resp.text()
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_err = e

        raise last_err or RuntimeError("Fetch fehlgeschlagen")
