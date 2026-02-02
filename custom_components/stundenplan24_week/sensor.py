from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coord = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SPlanWeekSensor(coord, entry)], True)


class SPlanWeekSensor(CoordinatorEntity):
    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry

        target = (entry.data.get("target") or "").strip()
        self._attr_unique_id = f"{entry.entry_id}_week"
        self._attr_name = f"Stundenplan Woche ({target})"
        self._attr_icon = "mdi:calendar-week"

    @property
    def native_value(self) -> str:
        return "ok" if self.coordinator.last_update_success else "error"

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data or {}

        rows_raw = data.get("rows", [])
        rows_ha: list[dict] = []

        def first_or_empty(val: str) -> str:
            if not val:
                return ""
            parts = [p.strip() for p in val.split("/") if p.strip()]
            return parts[0] if parts else ""

        for row in rows_raw:
            cells = row.get("cells", [])

            start = (row.get("start", "") or "").strip()
            end = (row.get("end", "") or "").strip()
            base_time = (row.get("time", "") or "").strip()

            # Karte kann Start/Ende aus "time" lesen – wir liefern es kombiniert
            if start and end:
                time_str = f"{base_time} {start}-{end}".strip()
            else:
                time_str = base_time

            rows_ha.append(
                {
                    "time": time_str,
                    "Mo": first_or_empty(cells[0]) if len(cells) > 0 else "",
                    "Di": first_or_empty(cells[1]) if len(cells) > 1 else "",
                    "Mi": first_or_empty(cells[2]) if len(cells) > 2 else "",
                    "Do": first_or_empty(cells[3]) if len(cells) > 3 else "",
                    "Fr": first_or_empty(cells[4]) if len(cells) > 4 else "",
                }
            )

        return {
            "rows": rows_raw,
            "meta": data.get("meta", {}),
            "rows_ha": rows_ha,
        }
