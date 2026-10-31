from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import Platform

from .const import DOMAIN
from .suite_coordinator import SuiteCoordinator
from .startup import schedule_initial_refresh

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.NUMBER]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    from .view import register_view_service
    register_view_service(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up stundenplan24_week from a config entry."""
    coordinator = SuiteCoordinator(hass, entry)
    deferred = coordinator.provider_name == "stundenplan24"
    coordinator.initial_refresh_pending = deferred
    if deferred:
        coordinator.last_update_success = False
    else:
        await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    # IMPORTANT: keep backwards compatible shape: hass.data[DOMAIN][entry_id] == coordinator
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    coordinator.async_watch_sources()
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    if deferred:
        schedule_initial_refresh(hass, entry, coordinator)
    return True


async def _async_options_updated(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok
