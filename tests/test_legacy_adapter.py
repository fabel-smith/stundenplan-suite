"""Exercise the adapter with a deterministic legacy fetch boundary."""
import asyncio
import importlib
import sys
import types
from datetime import date, datetime, timedelta, timezone

import pytest


@pytest.fixture
def providers(monkeypatch):
    # The existing network/HA coordinator is not executed in these unit tests.
    module = types.ModuleType('stundenplan24_week.coordinator')
    module.SPlanCoordinator = type('SPlanCoordinator', (), {})
    monkeypatch.setitem(sys.modules, module.__name__, module)
    sys.modules.pop('stundenplan24_week.providers', None)
    return importlib.import_module('stundenplan24_week.providers')


def test_preserves_existing_card_contract_and_offsets(providers):
    now = datetime(2026,9,17,6,tzinfo=timezone(timedelta(hours=2)))
    old = {'rows':[{'time':'1.','cells':['D','','','','']}],
           'rows_table':[{'time':'1.','Mo':'D','Di':'','Mi':'','Do':'','Fr':''}],
           'meta':{'class':'3c','week_start':'20260914','days':['20260914'],'no_plan':False}}
    class Legacy:
        target = '3c'
        async def _async_update_data(self):
            self.bundles = {'2026-09-17': ([(1,'D','T1','R1','07:45','08:30')],[], '',True)}
            return old
    p = providers.Stundenplan24Provider.__new__(providers.Stundenplan24Provider)
    p.legacy = Legacy()
    result = asyncio.run(p.fetch(date(2026,9,21),now))
    assert p.legacy.week_offset == 1
    assert result['rows'] == old['rows'] and result['rows_table'] == old['rows_table']
    assert all(result['meta'][k] == v for k,v in old['meta'].items())
    assert result['daily']['today']['first_start'].endswith('07:45:00+02:00')
    assert result['daily']['today']['routine_ready'] is False  # legacy completeness is unknown


def test_original_subject_teacher_room_retained_on_cancellation(providers):
    data = {'2026-09-17': ([(1,'D','T1','R1','07:45','08:30')],
                            [(1,'D\nentfällt','','','','')], '',True)}
    item = providers.normalize_stundenplan24(data,timezone.utc)[0]
    assert item.status == 'cancelled'
    assert item.original == {'subject':'D','teacher':'T1','room':'R1'}
    assert item.start.endswith('07:45:00+00:00')


def test_parallel_base_lessons_preserved(providers):
    data = {'2026-09-17': ([(1,'Religion','T1','R1','07:45','08:30'),
                           (1,'Ethik','T2','R2','07:45','08:30')], [],'',True)}
    assert len(providers.normalize_stundenplan24(data,timezone.utc)) == 2
