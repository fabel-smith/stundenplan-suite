"""Exercise platform startup without Home Assistant or live school requests."""
import asyncio
import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock

import pytest


@pytest.fixture
def platforms(monkeypatch):
    class Entity:
        async def async_added_to_hass(self):
            pass

        def async_write_ha_state(self):
            self.writes = getattr(self, "writes", 0) + 1

    class CoordinatorEntity(Entity):
        @classmethod
        def __class_getitem__(cls, item):
            return cls

        def __init__(self, coordinator):
            self.coordinator = coordinator

    class RestoreEntity(Entity):
        async def async_get_last_state(self):
            return self.last_state

    class NumberEntity(Entity):
        pass

    modules = {
        "homeassistant": {},
        "homeassistant.components": {},
        "homeassistant.components.sensor": {"SensorEntity": Entity},
        "homeassistant.components.number": {
            "NumberEntity": NumberEntity, "NumberMode": types.SimpleNamespace(BOX="box")},
        "homeassistant.config_entries": {"ConfigEntry": object},
        "homeassistant.core": {"HomeAssistant": object},
        "homeassistant.helpers": {},
        "homeassistant.helpers.entity_platform": {"AddEntitiesCallback": object},
        "homeassistant.helpers.entity_registry": {},
        "homeassistant.helpers.update_coordinator": {"CoordinatorEntity": CoordinatorEntity},
        "homeassistant.helpers.restore_state": {"RestoreEntity": RestoreEntity},
        "homeassistant.util": {"slugify": lambda value: value.lower()},
        "stundenplan24_week.suite_coordinator": {"SuiteCoordinator": object},
    }
    for name, values in modules.items():
        module = types.ModuleType(name)
        module.__dict__.update(values)
        monkeypatch.setitem(sys.modules, name, module)

    loaded = {}
    root = Path(__file__).resolve().parents[1] / "custom_components/stundenplan24_week"
    for name in ("sensor", "number"):
        # Separate module names avoid leaking mocked HA classes to other tests.
        spec = importlib.util.spec_from_file_location(f"stundenplan24_week._test_{name}", root / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        loaded[name] = module
    return types.SimpleNamespace(**loaded)


def context(provider="stundenplan24", offset=0):
    coordinator = types.SimpleNamespace(
        target="Demo", week_offset=offset, data={"rows": [{"time": "1."}]},
        async_request_refresh=AsyncMock())
    entry = types.SimpleNamespace(
        entry_id="demo", data={"target": "Demo", "provider": provider}, options={})
    hass = types.SimpleNamespace(data={"stundenplan24_week": {entry.entry_id: coordinator}})
    return hass, entry, coordinator


@pytest.mark.parametrize("provider", ["stundenplan24", "schulmanager"])
def test_sensors_reuse_completed_first_refresh(platforms, provider):
    hass, entry, coordinator = context(provider)
    added = []

    def add(entities, update_before_add=False):
        added.append((entities, update_before_add))

    asyncio.run(platforms.sensor.async_setup_entry(hass, entry, add))
    entities, update_before_add = added[0]
    assert len(entities) == 3
    assert all(entity.coordinator is coordinator for entity in entities)
    assert entities[0].native_value == "Plan verfügbar"
    assert update_before_add is False
    coordinator.async_request_refresh.assert_not_awaited()


@pytest.mark.parametrize("provider", ["stundenplan24", "schulmanager"])
@pytest.mark.parametrize("saved", [None, "0", "0.0", "unknown", "unavailable", "invalid"])
def test_restore_current_week_does_not_refetch(platforms, provider, saved):
    hass, entry, coordinator = context(provider)
    number = platforms.number.WeekOffsetNumber(hass, entry)
    number.last_state = types.SimpleNamespace(state=saved) if saved is not None else None
    asyncio.run(number.async_added_to_hass())
    assert number.native_value == 0
    assert coordinator.week_offset == 0
    assert number.writes == 1
    coordinator.async_request_refresh.assert_not_awaited()


@pytest.mark.parametrize("saved", [-1, 1])
def test_restore_other_week_refreshes_with_correct_offset(platforms, saved):
    hass, entry, coordinator = context()
    seen_offsets = []

    async def refresh():
        seen_offsets.append(coordinator.week_offset)

    coordinator.async_request_refresh.side_effect = refresh
    number = platforms.number.WeekOffsetNumber(hass, entry)
    number.last_state = types.SimpleNamespace(state=str(saved))
    asyncio.run(number.async_added_to_hass())
    assert number.native_value == saved
    assert seen_offsets == [saved]
    assert number.writes == 1


def test_restore_already_loaded_week_does_not_refetch(platforms):
    hass, entry, coordinator = context(offset=1)
    number = platforms.number.WeekOffsetNumber(hass, entry)
    number.last_state = types.SimpleNamespace(state="1")
    asyncio.run(number.async_added_to_hass())
    assert number.native_value == 1
    coordinator.async_request_refresh.assert_not_awaited()


def test_explicit_week_change_still_refreshes(platforms):
    hass, entry, coordinator = context()
    number = platforms.number.WeekOffsetNumber(hass, entry)
    asyncio.run(number.async_set_native_value(1))
    assert number.native_value == coordinator.week_offset == 1
    coordinator.async_request_refresh.assert_awaited_once()


def test_deferred_restore_does_not_block_platform_setup(platforms):
    hass, entry, coordinator = context()
    coordinator.initial_refresh_pending = True
    coordinator.data = None
    number = platforms.number.WeekOffsetNumber(hass, entry)
    number.last_state = types.SimpleNamespace(state="1")
    asyncio.run(number.async_added_to_hass())
    assert coordinator.week_offset == 1
    coordinator.async_request_refresh.assert_not_awaited()
    sensor = platforms.sensor.Stundenplan24WeekSensor(coordinator, entry)
    assert sensor.native_value == "Daten werden geladen"
