from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import slugify

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

CONF_TARGET = "target"

# Allowed offsets:
#  0 = aktuelle Woche
#  1 = nächste Woche
# -1 = letzte Woche (optional, falls du es später nutzen willst)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    target = (entry.data.get(CONF_TARGET) or entry.options.get(CONF_TARGET) or "").strip()
    if not target:
        _LOGGER.error("Missing '%s' in config entry %s", CONF_TARGET, entry.entry_id)
        return

    # ---- Entity-Registry Migration / Cleanup ----
    # Ziel: immer genau *eine* Number-Entity unter number.<target>_woche_offset,
    # ohne _2/_3-Duplikate aus früheren Versionen.
    desired_entity_id = f"number.{slugify(target)}_woche_offset"
    desired_unique_id = f"{DOMAIN}_{target}_week_offset"

    registry = er.async_get(hass)
    candidates = [
        e for e in registry.entities.values()
        if e.config_entry_id == entry.entry_id and e.domain == "number"
    ]

    # Entferne klare Duplikate (z.B. *_woche_offset_2), halte die "saubere" Entity-ID.
    dupes = [e for e in candidates if e.entity_id.startswith(desired_entity_id)]
    if len(dupes) > 1:
        # Bevorzugt: exakt desired_entity_id
        keep = next((e for e in dupes if e.entity_id == desired_entity_id), dupes[0])
        for e in dupes:
            if e.entity_id != keep.entity_id:
                _LOGGER.warning("Removing duplicate entity_id %s (keeping %s)", e.entity_id, keep.entity_id)
                registry.async_remove(e.entity_id)
        dupes = [keep]

    # Wenn es eine existente Registry-Entity gibt (egal ob _2), versuche sie auf
    # desired_entity_id + desired_unique_id zu normalisieren.
    if dupes:
        e = dupes[0]
        updates: dict[str, Any] = {}
        if e.unique_id != desired_unique_id:
            updates["new_unique_id"] = desired_unique_id
        # Entity-ID nur ändern, wenn sie nicht bereits korrekt ist und frei ist.
        if e.entity_id != desired_entity_id and desired_entity_id not in registry.entities:
            updates["new_entity_id"] = desired_entity_id
        if updates:
            registry.async_update_entity(e.entity_id, **updates)

    async_add_entities([WeekOffsetNumber(hass, entry)], True)


class WeekOffsetNumber(NumberEntity, RestoreEntity):
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = -1
    _attr_native_max_value = 1
    _attr_native_step = 1

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.target = (entry.data.get(CONF_TARGET) or entry.options.get(CONF_TARGET) or "").strip()

        # Stable unique_id -> verhindert _2/_3 in der Registry
        self._attr_unique_id = f"{DOMAIN}_{self.target}_week_offset"
        self._attr_name = f"{self.target} Woche Offset"
        self._attr_icon = "mdi:calendar-week"

        # Startwert
        self._native_value: float | None = 0.0

    @property
    def native_value(self) -> float | None:
        return self._native_value

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        # Restore last value if available
        last = await self.async_get_last_state()
        if last and last.state not in (None, "", "unknown", "unavailable"):
            try:
                self._native_value = float(last.state)
            except ValueError:
                self._native_value = 0.0
        else:
            self._native_value = 0.0

        # Push into coordinator (if already created)
        coord = self.hass.data.get(DOMAIN, {}).get(self.entry.entry_id)
        if coord is not None:
            coord.week_offset = int(self._native_value or 0)
            # sofort refresh, damit UI nach HA-Neustart nicht "zurückspringt"
            await coord.async_request_refresh()

        self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        # Validate / clamp
        try:
            v_int = int(round(float(value)))
        except Exception:
            v_int = 0
        v_int = max(int(self._attr_native_min_value), min(int(self._attr_native_max_value), v_int))

        self._native_value = float(v_int)

        coord = self.hass.data.get(DOMAIN, {}).get(self.entry.entry_id)
        if coord is not None:
            coord.week_offset = v_int
            await coord.async_request_refresh()

        self.async_write_ha_state()
