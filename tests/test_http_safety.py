"""Deterministic HTTP tests: never contact a school or external server."""
import asyncio
import importlib
import sys
import types
from datetime import datetime, timezone
from email.utils import format_datetime

import aiohttp
import pytest


@pytest.fixture
def network(monkeypatch):
    session = types.SimpleNamespace(calls=[], outcomes=[], active=0, peak=0)
    clock = types.SimpleNamespace(now=0.0)
    real_sleep = asyncio.sleep

    async def sleep(seconds):
        clock.now += seconds
        await real_sleep(0)

    class Response:
        def __init__(self, outcome):
            self.status, self.headers, self.body = outcome

        async def __aenter__(self):
            session.active += 1
            session.peak = max(session.peak, session.active)
            await real_sleep(0)
            return self

        async def __aexit__(self, *args):
            session.active -= 1

        def raise_for_status(self):
            if self.status >= 400:
                raise aiohttp.ClientResponseError(None, (), status=self.status)

        async def text(self):
            return self.body

    def get(url, **kwargs):
        session.calls.append((url, kwargs))
        outcome = session.outcomes.pop(0) if session.outcomes else (200, {}, "<plan/>")
        if isinstance(outcome, Exception):
            raise outcome
        return Response(outcome)

    session.get = get
    for name in ("homeassistant", "homeassistant.helpers", "homeassistant.helpers.aiohttp_client",
                 "homeassistant.config_entries", "homeassistant.core", "homeassistant.helpers.update_coordinator"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    sys.modules["homeassistant.helpers.aiohttp_client"].async_get_clientsession = lambda hass: session
    sys.modules["homeassistant.config_entries"].ConfigEntry = object
    sys.modules["homeassistant.core"].HomeAssistant = object

    class Coordinator:
        @classmethod
        def __class_getitem__(cls, item):
            return cls

        def __init__(self, *args, **kwargs):
            pass

    update = sys.modules["homeassistant.helpers.update_coordinator"]
    update.DataUpdateCoordinator = Coordinator
    update.UpdateFailed = type("UpdateFailed", (Exception,), {})
    for name in ("stundenplan24_week.stundenplan24_api", "stundenplan24_week.coordinator"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    api = importlib.import_module("stundenplan24_week.stundenplan24_api")
    coordinator = importlib.import_module("stundenplan24_week.coordinator")
    monkeypatch.setattr(api.time, "monotonic", lambda: clock.now)
    monkeypatch.setattr(api.asyncio, "sleep", sleep)
    hass = types.SimpleNamespace(data={})
    client = api.Stundenplan24Api(hass, "example", "not-a-real-password")
    yield types.SimpleNamespace(api=api, client=client, session=session, clock=clock,
                               hass=hass, coordinator=coordinator, update=update)


@pytest.mark.parametrize("status", [401, 403])
def test_access_denial_stops_retries_and_fallbacks_until_reload(network, status):
    async def scenario():
        n = network
        n.session.outcomes = [(status, {}, "denied")]
        with pytest.raises(n.api.Stundenplan24RequestBlocked, match=str(status)):
            await n.client.fetch_wplan_day_xml("example", "2026-09-25")
        n.clock.now += 86400
        with pytest.raises(n.api.Stundenplan24RequestBlocked):
            await n.client.fetch_text("https://www.stundenplan24.de/other")
        assert len(n.session.calls) == 1
        reloaded = n.api.Stundenplan24Api(n.hass, "corrected", "example")
        await reloaded.fetch_text("https://www.stundenplan24.de/other")
        assert len(n.session.calls) == 2
    asyncio.run(scenario())


@pytest.mark.parametrize("status", [429, 503])
def test_retry_after_is_shared_across_entries(network, status):
    async def scenario():
        n = network
        other = n.api.Stundenplan24Api(n.hass, "other", "example")
        n.session.outcomes = [(status, {"Retry-After": "120"}, "busy")]
        results = await asyncio.gather(n.client.fetch_text("one"), other.fetch_text("two"),
                                       return_exceptions=True)
        assert all(isinstance(x, n.api.Stundenplan24RequestBlocked) for x in results)
        assert len(n.session.calls) == 1
        n.clock.now = 119
        with pytest.raises(n.api.Stundenplan24RequestBlocked):
            await other.fetch_text("two")
        n.clock.now = 121
        assert await other.fetch_text("two") == "<plan/>"
        assert len(n.session.calls) == 2
    asyncio.run(scenario())


def test_default_backoff_grows_on_repeated_rate_limits(network):
    async def scenario():
        n = network
        n.session.outcomes = [(429, {}, "busy"), (429, {}, "busy")]
        with pytest.raises(n.api.Stundenplan24RequestBlocked):
            await n.client.fetch_text("one")
        assert n.client._gate.blocked_until == 60
        n.clock.now = 61
        with pytest.raises(n.api.Stundenplan24RequestBlocked):
            await n.client.fetch_text("two")
        assert n.client._gate.blocked_until == 181
    asyncio.run(scenario())


def test_retry_after_dates_and_invalid_values(network, monkeypatch):
    monkeypatch.setattr(network.api.time, "time", lambda: 1800000000)
    value = format_datetime(datetime.fromtimestamp(1800000090, timezone.utc), usegmt=True)
    assert network.api.retry_after_seconds(value) == 90
    assert network.api.retry_after_seconds("0") == 1
    assert network.api.retry_after_seconds("-1") == 1
    for bad in (None, "", "NaN", "inf", "invalid-date"):
        assert network.api.retry_after_seconds(bad) is None


@pytest.mark.parametrize("status", [400, 404])
def test_non_retryable_http_error_is_attempted_once(network, status):
    async def scenario():
        network.session.outcomes = [(status, {}, "missing")]
        with pytest.raises(aiohttp.ClientResponseError):
            await network.client.fetch_text("missing")
        assert len(network.session.calls) == 1
    asyncio.run(scenario())


def test_missing_optional_file_still_uses_existing_fallback(network):
    async def scenario():
        network.session.outcomes = [(404, {}, ""), (200, {}, "fallback")]
        assert await network.client.fetch_wplan_day_xml("example", "2026-09-25") == "fallback"
        assert len(network.session.calls) == 2
        assert "mobil" in network.session.calls[1][0]
    asyncio.run(scenario())


@pytest.mark.parametrize("outcome", [(500, {}, "error"), asyncio.TimeoutError()])
def test_transient_failure_retries_with_delay_then_cools_down(network, outcome):
    async def scenario():
        n = network
        n.session.outcomes = [outcome, outcome]
        with pytest.raises(n.api.Stundenplan24RequestBlocked):
            await n.client.fetch_text("one")
        assert len(n.session.calls) == 2
        assert n.clock.now >= 2
        with pytest.raises(n.api.Stundenplan24RequestBlocked):
            await n.client.fetch_text("two")
        assert len(n.session.calls) == 2
    asyncio.run(scenario())


def test_successful_retry_does_not_block_client(network):
    async def scenario():
        n = network
        n.session.outcomes = [(500, {}, "error"), (200, {}, "ok")]
        assert await n.client.fetch_text("one") == "ok"
        n.client.raise_if_blocked()
        assert n.clock.now >= 2
    asyncio.run(scenario())


def test_serialization_cache_expiry_and_credential_isolation(network):
    async def scenario():
        n = network
        assert await asyncio.gather(*(n.client.fetch_text("same") for _ in range(10))) == ["<plan/>"] * 10
        assert len(n.session.calls) == 1
        other = n.api.Stundenplan24Api(n.hass, "other", "example")
        await other.fetch_text("same")
        assert len(n.session.calls) == 2
        n.clock.now += n.api.CACHE_SECONDS + 1
        await asyncio.gather(*(n.client.fetch_text(str(i)) for i in range(5)))
        assert n.session.peak == 1
        await n.client.fetch_text("same")
        assert len(n.session.calls) == 8
        assert n.clock.now >= 33
    asyncio.run(scenario())


def test_cache_size_is_bounded_and_urls_are_stable(network, monkeypatch):
    async def scenario():
        n = network
        monkeypatch.setattr(n.api, "CACHE_LIMIT", 2)
        for url in ("one", "two", "three"):
            await n.client.fetch_text(url)
        assert len(n.client._cache) == 2
        assert n.client.url_vplan_kl_day_xml("example", "2026-09-25").endswith("VplanKl20260925.xml")
        assert n.client._base_headers()["User-Agent"] == (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0 Safari/537.36"
        )
    asyncio.run(scenario())


@pytest.mark.parametrize("method,args", [
    ("_fetch_mobil_plan_lessons", (datetime(2026, 9, 25),)),
    ("_fetch_vplan_overlay_lessons", (datetime(2026, 9, 25),)),
    ("_fetch_wplan_info", (datetime(2026, 9, 25),)),
    ("_fetch_wplan_day_overlay_lessons", (datetime(2026, 9, 25),)),
    ("_fetch_indiware_basis", ()),
    ("_ensure_indiware_week", (datetime(2026, 9, 21),)),
    ("_fetch_wplan_html_week_map", (datetime(2026, 9, 21),)),
])
def test_coordinator_does_not_swallow_blocked_fetches(network, method, args):
    async def scenario():
        n = network
        entry = types.SimpleNamespace(data={"school_id": "example", "target": "Demo"}, options={})
        coordinator = n.coordinator.SPlanCoordinator(n.hass, entry)
        n.session.outcomes = [(429, {}, "busy")]
        with pytest.raises(n.api.Stundenplan24RequestBlocked):
            await getattr(coordinator, method)(*args)
        assert len(n.session.calls) == 1
    asyncio.run(scenario())


def test_blocked_update_is_failure_not_an_empty_timetable(network):
    async def scenario():
        n = network
        entry = types.SimpleNamespace(data={"school_id": "example", "target": "Demo"}, options={})
        coordinator = n.coordinator.SPlanCoordinator(n.hass, entry)
        n.session.outcomes = [(429, {}, "busy")]
        with pytest.raises(n.update.UpdateFailed, match="HTTP 429"):
            await coordinator._async_update_data()
        with pytest.raises(n.update.UpdateFailed):
            await coordinator._async_update_data()
        assert len(n.session.calls) == 1
    asyncio.run(scenario())
