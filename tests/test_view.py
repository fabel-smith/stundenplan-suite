from copy import deepcopy
from datetime import date, timedelta

import pytest

from stundenplan24_week.view import cached_view
from stundenplan24_week.model import compact_week_attributes
from test_schedule_service import NOW, DAY, lesson, student, result


def adjacent_data(config=None):
    source = student()
    next_day = DAY + timedelta(days=7)
    source['days'][7]['lessons'] = [lesson(date=next_day.isoformat(), subject='Ku',
        start=f'{next_day}T09:00:00+01:00', end=f'{next_day}T09:45:00+01:00')]
    return result(source, config)


def test_view_is_date_bound_and_does_not_mutate_selected_week():
    data = adjacent_data()
    before = deepcopy(data)
    view = cached_view(data, ['2026-11-02', '2026-11-09'], {}, NOW)
    assert view['weeks']['2026-11-02'][0]['Mo'] == 'Ph\nEDV1'
    assert view['weeks']['2026-11-09'][0]['Mo'] == 'Ku\nEDV1'
    assert data == before
    assert 'view_loaded_days' not in compact_week_attributes(data)


def test_missing_day_and_stale_data_never_reuse_another_week():
    data = adjacent_data()
    view = cached_view(data, ['2026-11-16'], {}, NOW)
    assert view['loaded_days'] == []
    assert view['weeks']['2026-11-16'] == []
    stale = cached_view(data, ['2026-11-09'], {}, NOW + timedelta(hours=2))
    assert stale['loaded_days'] == []
    assert stale['weeks']['2026-11-09'] == []


def test_weekday_and_global_exclusions_are_preserved():
    data = adjacent_data({'excluded_course_weekdays': {'10': ['mon']}})
    view = cached_view(data, ['2026-11-02', '2026-11-09'], {}, NOW)
    assert all(not rows for rows in view['weeks'].values())
    assert len(view['loaded_days']) == 2


def test_legacy_only_serves_the_actual_cached_week():
    data = {'meta': {'week_start': '20261102', 'days': ['20261102']},
            'rows_table': [{'time': '1.', 'Mo': 'Old'}]}
    view = cached_view(data, ['2026-11-02', '2026-11-09'], {}, NOW)
    assert view['weeks']['2026-11-02'] == data['rows_table']
    assert view['weeks']['2026-11-09'] == []
    assert view['loaded_days'] == ['2026-11-02']


@pytest.mark.parametrize('requested', [[], ['bad'], ['2026-12-31'],
    [(DAY + timedelta(days=i)).isoformat() for i in range(22)]])
def test_invalid_ranges_rejected(requested):
    with pytest.raises(ValueError):
        cached_view(adjacent_data(), requested, {}, NOW)


def test_service_is_read_only_and_checks_sensor_and_permissions(monkeypatch):
    import asyncio
    import sys
    import types
    from unittest.mock import AsyncMock, Mock
    from stundenplan24_week.view import register_view_service

    class Denied(Exception):
        def __init__(self, **kwargs):
            super().__init__('denied')

    record = types.SimpleNamespace(platform='stundenplan24_week', domain='sensor',
        unique_id='test_woche', config_entry_id='entry')
    registry = types.SimpleNamespace(async_get=lambda entity: record)
    modules = {
        'homeassistant.auth': {}, 'homeassistant.auth.permissions': {},
        'homeassistant.auth.permissions.const': {'POLICY_READ': 'read'},
        'homeassistant.core': {'SupportsResponse': types.SimpleNamespace(ONLY='only')},
        'homeassistant.exceptions': {'ServiceValidationError': ValueError, 'Unauthorized': Denied},
        'homeassistant.helpers': {},
        'homeassistant.helpers.config_validation': {'entity_id': str},
        'homeassistant.helpers.entity_registry': {'async_get': lambda hass: registry},
        'homeassistant.util': {}, 'homeassistant.util.dt': {'now': lambda: NOW},
    }
    for name, values in modules.items():
        module = types.ModuleType(name)
        module.__dict__.update(values)
        monkeypatch.setitem(sys.modules, name, module)
    permissions = types.SimpleNamespace(check_entity=Mock(return_value=True))
    coordinator = types.SimpleNamespace(data=adjacent_data(), last_update_success=True,
        entry=types.SimpleNamespace(data={}, options={}), async_request_refresh=AsyncMock())
    services = types.SimpleNamespace(has_service=Mock(return_value=False), async_register=Mock())
    hass = types.SimpleNamespace(services=services,
        auth=types.SimpleNamespace(async_get_user=AsyncMock(return_value=types.SimpleNamespace(permissions=permissions))),
        data={'stundenplan24_week': {'entry': coordinator}})
    register_view_service(hass)
    args, kwargs = services.async_register.call_args
    assert kwargs['supports_response'] == 'only'
    handler = args[2]
    call = types.SimpleNamespace(context=types.SimpleNamespace(user_id='user'),
        data={'entity_id': 'sensor.test', 'dates': ['2026-11-09']})
    assert asyncio.run(handler(call))['loaded_days'] == ['2026-11-09']
    coordinator.async_request_refresh.assert_not_awaited()
    permissions.check_entity.return_value = False
    with pytest.raises(Denied):
        asyncio.run(handler(call))
    permissions.check_entity.return_value = True
    record.platform = 'other'
    with pytest.raises(ValueError, match='Suite week sensor'):
        asyncio.run(handler(call))
    record.platform = 'stundenplan24_week'
    coordinator.last_update_success = False
    with pytest.raises(ValueError, match='not available'):
        asyncio.run(handler(call))
