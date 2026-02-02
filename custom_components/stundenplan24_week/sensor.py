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
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([StundenplanWeekSensor(coordinator, entry)], True)


class StundenplanWeekSensor(CoordinatorEntity):
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

        show_room = self._entry.options.get("show_room", True)
        show_teacher = self._entry.options.get("show_teacher", False)

        days = data.get("days") or []

        weekday_map = {
            "Montag": "Mo",
            "Dienstag": "Di",
            "Mittwoch": "Mi",
            "Donnerstag": "Do",
            "Freitag": "Fr",
        }

        by_hour: dict[int, dict] = {}

        def fmt_cell(fach: str, raum: str, lehrer: str, info: str) -> str:
            fach = (fach or "").strip()
            raum = (raum or "").strip()
            lehrer = (lehrer or "").strip()
            info = (info or "").strip()

            extras = []
            if show_room and raum:
                extras.append(raum)
            if show_teacher and lehrer:
                extras.append(lehrer)

            cell = fach
            if cell and extras:
                cell = f"{cell} ({' · '.join(extras)})"

            if info and (fach == "" or fach.upper() == "AUSFALL"):
                cell = (cell + " — " if cell else "") + info

            return cell

        for day in days:
            date_label = (day.get("da_
