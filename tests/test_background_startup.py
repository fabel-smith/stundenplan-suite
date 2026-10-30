"""Lifecycle and per-refresh reuse without live school requests."""
import ast
import asyncio
import importlib.util
from pathlib import Path
import sys
import types
from unittest.mock import AsyncMock

import pytest

ROOT = Path(__file__).resolve().parents[1] / "custom_components/stundenplan24_week"


@pytest.fixture
def startup(monkeypatch):
    callbacks = []
    def at_started(hass, cb):
        if hass.running:
            cb(hass)
            return lambda: None
        callbacks.append(cb)
        return lambda: callbacks.remove(cb) if cb in callbacks else None
    for name, attrs in {
        "homeassistant.core": {"callback": lambda f: f},
        "homeassistant.helpers.start": {"async_at_started": at_started},
    }.items():
        module = types.ModuleType(name)
        module.__dict__.update(attrs)
        monkeypatch.setitem(sys.modules, name, module)
    spec = importlib.util.spec_from_file_location("test_background_helper", ROOT / "startup.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, callbacks


class Entry:
    def __init__(self):
        self.tasks = []
        self.unloads = []
    def async_on_unload(self, cb):
        self.unloads.append(cb)
    def async_create_background_task(self, hass, coro, name, eager_start):
        assert eager_start is False
        self.tasks.append(asyncio.create_task(coro))
    def unload(self):
        for cb in self.unloads:
            cb()
        for task in self.tasks:
            task.cancel()


@pytest.mark.parametrize("running", [False, True])
def test_nonblocking_start_and_unload(startup, running):
    module, callbacks = startup
    async def run():
        hass = types.SimpleNamespace(running=running)
        entry = Entry()
        gate = asyncio.Event()
        coord = types.SimpleNamespace(data=None, initial_refresh_pending=True, last_update_success=False)
        coord.async_request_refresh = AsyncMock(side_effect=gate.wait)
        module.schedule_initial_refresh(hass, entry, coord)
        coord.async_request_refresh.assert_not_awaited()
        if not running:
            assert not entry.tasks
            callbacks[0](hass)
        await asyncio.sleep(0)
        coord.async_request_refresh.assert_awaited_once()
        assert not entry.tasks[0].done()
        entry.unload()
        await asyncio.gather(*entry.tasks, return_exceptions=True)
        assert entry.tasks[0].cancelled()
    asyncio.run(run())


def test_unload_before_started_removes_listener(startup):
    module, callbacks = startup
    entry = Entry()
    module.schedule_initial_refresh(types.SimpleNamespace(running=False), entry, object())
    entry.unload()
    assert callbacks == [] and entry.tasks == []


def test_initial_failure_retries_then_stops(startup, monkeypatch):
    module, _ = startup
    delays = []
    async def sleep(delay):
        delays.append(delay)
    monkeypatch.setattr(module, "asyncio", types.SimpleNamespace(sleep=sleep))
    async def run():
        entry = Entry()
        coord = types.SimpleNamespace(data=None, last_update_success=False)
        async def refresh():
            if delays:
                coord.data = {"rows": []}
                coord.last_update_success = True
        coord.async_request_refresh = AsyncMock(side_effect=refresh)
        module.schedule_initial_refresh(types.SimpleNamespace(running=True), entry, coord)
        await entry.tasks[0]
        assert delays == [60]
        assert coord.async_request_refresh.await_count == 2
        assert coord.data == {"rows": []}
    asyncio.run(run())


def info_method():
    # Execute the actual small cache boundary without importing HA/parser code.
    tree = ast.parse((ROOT / "coordinator.py").read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "SPlanCoordinator")
    method = next(n for n in cls.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "_fetch_wplan_info")
    ns = {"ymd": str}
    unit = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), method], type_ignores=[])
    exec(compile(ast.fix_missing_locations(unit), "cache-boundary", "exec"), ns)
    return ns["_fetch_wplan_info"]


@pytest.mark.parametrize("result", [{}, {(1, 1): "Info"}])
def test_optional_results_reused_only_in_refresh(result):
    async def run():
        obj = types.SimpleNamespace(_refresh_wplan_info={}, _load_wplan_info=AsyncMock(return_value=result))
        fetch = info_method()
        assert await fetch(obj, "day") == result
        assert await fetch(obj, "day") == result
        obj._load_wplan_info.assert_awaited_once()
        obj._refresh_wplan_info = {}
        await fetch(obj, "day")
        assert obj._load_wplan_info.await_count == 2
    asyncio.run(run())


def test_access_errors_are_not_cached():
    async def run():
        obj = types.SimpleNamespace(_refresh_wplan_info={}, _load_wplan_info=AsyncMock(side_effect=RuntimeError("blocked")))
        with pytest.raises(RuntimeError, match="blocked"):
            await info_method()(obj, "day")
        assert obj._refresh_wplan_info == {}
    asyncio.run(run())


@pytest.mark.parametrize("provider", ["stundenplan24", "schulmanager"])
def test_entry_setup_only_defers_remote_provider(startup, monkeypatch, provider):
    _, callbacks = startup
    coord = types.SimpleNamespace(
        provider_name=provider, data=None, last_update_success=True,
        async_config_entry_first_refresh=AsyncMock(), async_watch_sources=lambda: None,
    )
    for name, attrs in {
        "homeassistant.config_entries": {"ConfigEntry": object},
        "homeassistant.const": {"Platform": types.SimpleNamespace(SENSOR="sensor", NUMBER="number")},
        "stundenplan24_week.suite_coordinator": {"SuiteCoordinator": lambda h, e: coord},
        "stundenplan24_week.startup": {"schedule_initial_refresh": startup[0].schedule_initial_refresh},
    }.items():
        module = types.ModuleType(name)
        module.__dict__.update(attrs)
        monkeypatch.setitem(sys.modules, name, module)
    sys.modules["homeassistant.core"].HomeAssistant = object
    spec = importlib.util.spec_from_file_location("stundenplan24_week._test_entry", ROOT / "__init__.py")
    spec.submodule_search_locations = None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    async def run():
        entry = Entry()
        entry.entry_id = "test"
        entry.add_update_listener = lambda cb: lambda: None
        hass = types.SimpleNamespace(running=False, data={})
        async def forward(entry, platforms):
            assert hass.data["stundenplan24_week"]["test"] is coord
            if provider == "stundenplan24":
                assert coord.initial_refresh_pending and not coord.last_update_success
                coord.async_config_entry_first_refresh.assert_not_awaited()
        hass.config_entries = types.SimpleNamespace(async_forward_entry_setups=forward)
        assert await module.async_setup_entry(hass, entry)
        if provider == "schulmanager":
            coord.async_config_entry_first_refresh.assert_awaited_once()
            assert callbacks == []
        else:
            assert len(callbacks) == 1
        entry.unload()
    asyncio.run(run())
