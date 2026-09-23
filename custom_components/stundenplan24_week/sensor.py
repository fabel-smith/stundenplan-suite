from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .model import compact_week_attributes
from .suite_coordinator import SuiteCoordinator as SPlanCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SPlanCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([Stundenplan24WeekSensor(coordinator, entry),
                        DailySensor(coordinator, entry, "today"),
                        DailySensor(coordinator, entry, "tomorrow")], update_before_add=True)


class Stundenplan24WeekSensor(CoordinatorEntity[SPlanCoordinator], SensorEntity):
    _attr_icon = "mdi:calendar-week"
    _attr_has_entity_name = True

    def __init__(self, coordinator: SPlanCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self.entry = entry

        target = (coordinator.target or "klasse").strip()

        # eindeutige ID + Name
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_{target}_woche"
        self._attr_name = f"{target} Woche"

        # Optional: wenn du willst, dass die Entity-ID im Editor eher "sprechend" wird,
        # setze den Namen um (HA generiert entity_id dann neu nur bei Neuanlage).
        # self._attr_name = f"Stundenplan Woche {target}"

    @property
    def native_value(self) -> str:
        """Kurzer Status als Sensorwert."""
        data = self.coordinator.data or {}
        meta = data.get("meta") or {}
        no_plan = bool(meta.get("no_plan", False))

        if no_plan:
            return "Kein Plan"

        rows = data.get("rows") or []
        return "Plan verfügbar" if rows else "Kein Plan"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        attrs = compact_week_attributes(data)

        from homeassistant.helpers import entity_registry as er
        offset_uid = (f"{DOMAIN}_{self.entry.entry_id}_week_offset" if self.entry.data.get("provider") == "schulmanager"
                      else f"{DOMAIN}_{self.coordinator.target}_week_offset")
        attrs["week_offset_entity"] = er.async_get(self.hass).async_get_entity_id("number", DOMAIN, offset_uid)
        return attrs


class DailySensor(CoordinatorEntity[SPlanCoordinator], SensorEntity):
    """Date-bound summaries independent of the card's selected week."""
    _attr_has_entity_name = True
    _attr_icon = "mdi:school"

    def __init__(self, coordinator, entry, day):
        super().__init__(coordinator)
        self.day = day
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_{day}"
        self._attr_name = f"{coordinator.target} Unterricht {'heute' if day == 'today' else 'morgen'}"

    @property
    def native_value(self):
        return self.extra_state_attributes.get("school_day", "unknown")

    @property
    def extra_state_attributes(self):
        from homeassistant.util import dt as dt_util
        from datetime import timedelta
        day = dt_util.now().date() + timedelta(days=self.day == "tomorrow")
        data = ((self.coordinator.data or {}).get("daily") or {}).get(self.day, {})
        if data.get("date") != day.isoformat():
            return {"date": day.isoformat(), "school_day": "unknown", "routine_ready": False,
                    "first_start": None, "last_end": None, "subjects": [], "coverage": "stale"}
        return {**data, "provider": self.coordinator.provider_name, "schema_version": 1}
