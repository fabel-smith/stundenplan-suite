from __future__ import annotations

import json
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SPlanCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SPlanCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([Stundenplan24WeekSensor(coordinator, entry)], update_before_add=True)


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

        rows = data.get("rows") or []
        rows_table = data.get("rows_table") or []  # NEU: Legacy-Format Mo/Di/Mi/Do/Fr

        meta = data.get("meta") or {}

        attrs: dict[str, Any] = {
            # neues Format
            "rows": rows,
            "meta": meta,

            # Rückwärtskompatibilität / Aliase
            "rows_ha": rows,
            "meta_ha": meta,

            # Legacy: Card-Source-Modus erwartet Keys "Mo".."Fr"
            "rows_table": rows_table,
        }

        # JSON-Strings (manche Karten/Templating nutzen lieber Strings)
        try:
            attrs["rows_json"] = json.dumps(rows, ensure_ascii=False)
        except Exception:
            attrs["rows_json"] = "[]"

        try:
            attrs["meta_json"] = json.dumps(meta, ensure_ascii=False)
        except Exception:
            attrs["meta_json"] = "{}"

        try:
            attrs["rows_table_json"] = json.dumps(rows_table, ensure_ascii=False)
        except Exception:
            attrs["rows_table_json"] = "[]"

        # Bequeme “Meta”-Attribute oben rausziehen
        if isinstance(meta, dict):
            for k in ("week_start", "days", "class", "school_id", "no_plan"):
                if k in meta:
                    attrs[k] = meta.get(k)

        return attrs
