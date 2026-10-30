"""Exercise the options wizard without a running HA installation."""
import asyncio
import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock

import pytest


@pytest.fixture
def flow_module(monkeypatch):
    class Flow:
        def __init_subclass__(cls, **kwargs):
            pass

        def async_show_form(self, **kwargs):
            return {"type": "form", **kwargs}

        def async_abort(self, **kwargs):
            return {"type": "abort", **kwargs}

        def async_create_entry(self, **kwargs):
            return {"type": "create_entry", **kwargs}

    class Selector:
        def __init__(self, config):
            self.config = config

        def __call__(self, value):
            return value

    selector = types.SimpleNamespace(SelectSelector=Selector, EntitySelector=Selector,
        SelectSelectorConfig=lambda **kw: kw, EntitySelectorConfig=lambda **kw: kw,
        SelectSelectorMode=types.SimpleNamespace(DROPDOWN="dropdown", LIST="list"))
    modules = {
        "homeassistant": {"config_entries": types.SimpleNamespace(ConfigFlow=Flow, OptionsFlow=Flow, ConfigEntry=object)},
        "homeassistant.core": {"callback": lambda f: f},
        "homeassistant.const": {"CONF_PASSWORD": "password", "CONF_USERNAME": "username"},
        "homeassistant.helpers": {"selector": selector},
    }
    for name, attrs in modules.items():
        module = types.ModuleType(name)
        module.__dict__.update(attrs)
        monkeypatch.setitem(sys.modules, name, module)
    path = Path(__file__).resolve().parents[1] / "custom_components/stundenplan24_week/config_flow.py"
    spec = importlib.util.spec_from_file_location("stundenplan24_week._test_schedule_flow", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def setup_flow(module, options=None, available=True):
    entry = types.SimpleNamespace(data={"provider": "schulmanager", "target": "Demo",
        "calendar_entity": "calendar.demo", "today_entity": "sensor.today",
        "tomorrow_entity": "sensor.tomorrow", "week_entity": "sensor.week"}, options=options or {})
    flow = module.OptionsFlowHandler(entry)
    student = {"config_entry_id": "account", "student_id": "child", "name": "Demo", "days": []}
    call = AsyncMock(return_value={"schema_version": 1, "source": "schulmanager", "students": [student]})
    flow.hass = types.SimpleNamespace(services=types.SimpleNamespace(
        has_service=lambda *a: available, async_call=call))
    return flow


def test_switch_existing_entry_keeps_sensor_options_and_uses_explicit_child(flow_module):
    f = setup_flow(flow_module, {"show_teacher": True, "update_minutes": 15})
    init = asyncio.run(f.async_step_init())
    assert init["type"] == "form"
    child = asyncio.run(f.async_step_init({"use_schedule_service": True, "show_room": False}))
    assert child["step_id"] == "schedule_child"
    invalid = asyncio.run(f.async_step_schedule_child({"student": "wrong:child"}))
    assert invalid["errors"]["base"] == "invalid_student"
    courses = asyncio.run(f.async_step_schedule_child({"student": "account:child"}))
    assert courses["step_id"] == "schedule_courses"
    done = asyncio.run(f.async_step_schedule_courses({"excluded_course_ids": []}))
    assert done["data"]["schedule_entry_id"] == "account"
    assert done["data"]["schedule_student_id"] == "child"
    assert done["data"]["show_teacher"] is True
    assert done["data"]["update_minutes"] == 15
    assert f._entry.data["calendar_entity"] == "calendar.demo"


def test_service_unavailable_does_not_save_partial_options(flow_module):
    f = setup_flow(flow_module, available=False)
    assert asyncio.run(f.async_step_init({"use_schedule_service": True}))["reason"] == "schedule_unavailable"


def test_change_child_clears_only_child_specific_filter(flow_module):
    f = setup_flow(flow_module, {"schedule_entry_id": "other", "schedule_student_id": "child", "excluded_course_ids": ["10"]})
    asyncio.run(f.async_step_init({"use_schedule_service": True}))
    asyncio.run(f.async_step_schedule_child({"student": "account:child"}))
    assert f._schedule_pending["excluded_course_ids"] == []


def test_saved_excluded_course_survives_empty_week(flow_module):
    f = setup_flow(flow_module, {"schedule_entry_id": "account", "schedule_student_id": "child", "excluded_course_ids": ["10"]})
    asyncio.run(f.async_step_init({"use_schedule_service": True}))
    asyncio.run(f.async_step_schedule_child({"student": "account:child"}))
    done = asyncio.run(f.async_step_schedule_courses({"excluded_course_ids": ["10"]}))
    assert done["data"]["excluded_course_ids"] == ["10"]


def test_old_mode_still_saves_without_service(flow_module):
    f = setup_flow(flow_module, available=False)
    form = asyncio.run(f.async_step_init({"use_schedule_service": False}))
    assert form["step_id"] == "legacy_sources"
    done = asyncio.run(f.async_step_legacy_sources(form["data_schema"]({})))
    assert done["type"] == "create_entry"
    assert done["data"]["use_schedule_service"] is False


@pytest.mark.parametrize("active", [False, True])
def test_initial_schulmanager_options_have_no_legacy_selectors(flow_module, active):
    f = setup_flow(flow_module, {"use_schedule_service": active})
    form = asyncio.run(f.async_step_init())
    assert form["step_id"] == "schulmanager_options"
    assert {key.schema for key in form["data_schema"].schema} == {
        "use_schedule_service", "show_room", "show_teacher", "update_minutes"}
    next_step = asyncio.run(f.async_step_schulmanager_options({"use_schedule_service": True}))
    assert next_step["step_id"] == "schedule_child"


def test_switch_back_from_new_entry_requests_sources_without_losing_filters(flow_module):
    f = setup_flow(flow_module, {"use_schedule_service": True, "excluded_course_ids": ["10"]})
    f._entry.data = {"provider": "schulmanager", "target": "Demo"}
    form = asyncio.run(f.async_step_schulmanager_options({"use_schedule_service": False, "show_room": False}))
    assert form["step_id"] == "legacy_sources"
    invalid = asyncio.run(f.async_step_legacy_sources({}))
    assert invalid["errors"]["base"] == "legacy_sources_required"
    values = dict(calendar_entity="calendar.demo", today_entity="sensor.today",
                  tomorrow_entity="sensor.tomorrow", week_entity="sensor.week")
    done = asyncio.run(f.async_step_legacy_sources(values))
    assert done["data"]["excluded_course_ids"] == ["10"]
    assert done["data"]["show_room"] is False
    assert done["data"]["use_schedule_service"] is False


def test_legacy_optional_changes_can_be_cleared(flow_module):
    f = setup_flow(flow_module, {"changes_entity": "sensor.old"})
    asyncio.run(f.async_step_init({"use_schedule_service": False}))
    values = {k: f._entry.data[k] for k in ("calendar_entity", "today_entity", "tomorrow_entity", "week_entity")}
    done = asyncio.run(f.async_step_legacy_sources(values))
    assert done["data"]["changes_entity"] == ""
