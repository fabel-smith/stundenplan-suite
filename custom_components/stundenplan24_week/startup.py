"""Load remote timetables without holding up Home Assistant startup."""
import asyncio
import logging
from time import monotonic

from homeassistant.core import callback
from homeassistant.helpers.start import async_at_started

_LOGGER = logging.getLogger(__name__)


def schedule_initial_refresh(hass, entry, coordinator):
    """Use HA's cancellable entry lifecycle, including reloads after startup."""
    async def refresh():
        coordinator.initial_refresh_pending = False
        delay = 60
        while coordinator.data is None:
            started = monotonic()
            await coordinator.async_request_refresh()
            _LOGGER.info(
                "Initial timetable refresh: success=%s, duration=%.1fs",
                coordinator.last_update_success, monotonic() - started,
            )
            if coordinator.data is not None:
                return
            # Do not leave an initial network failure unavailable for six hours.
            # The provider's shared rate-limit/backoff gate still applies.
            await asyncio.sleep(delay)
            delay = min(delay * 2, 600)

    @callback
    def start(_hass):
        entry.async_create_background_task(
            hass, refresh(), "stundenplan initial refresh", eager_start=False,
        )

    entry.async_on_unload(async_at_started(hass, start))
