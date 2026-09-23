"""Shared polling and entity contract for all timetable providers."""
from datetime import timedelta
import logging

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util

from .providers import Stundenplan24Provider
from .schulmanager import SchulmanagerProvider

_LOGGER = logging.getLogger(__name__)


class SuiteCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry):
        self.entry = entry
        self.target = entry.data.get("target", entry.title)
        self.week_offset = 0
        self.provider_name = entry.data.get("provider", "stundenplan24")
        config = {**entry.data, **entry.options}
        default_interval = 5 if self.provider_name == "schulmanager" else 360
        self.provider = (SchulmanagerProvider(hass, config) if self.provider_name == "schulmanager"
                         else Stundenplan24Provider(hass, entry))
        super().__init__(hass, _LOGGER, name=f"stundenplan_suite_{self.target}",
                         update_interval=timedelta(minutes=int(config.get("update_minutes", default_interval))))

    def async_watch_sources(self):
        if self.provider_name == "schulmanager":
            async def changed(event):
                await self.async_request_refresh()
            self.entry.async_on_unload(async_track_state_change_event(
                self.hass, self.provider.entity_ids, changed))

    async def _async_update_data(self):
        now = dt_util.now()
        monday = now.date() - timedelta(days=now.weekday()) + timedelta(weeks=self.week_offset)
        try:
            return await self.provider.fetch(monday, now)
        except Exception as err:
            raise UpdateFailed(f"{self.provider_name}: {err}") from err
