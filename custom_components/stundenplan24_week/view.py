"""Date-bound card views from cached data, without changing the shared week."""
from dataclasses import fields
from datetime import date, datetime, timedelta

from .model import Lesson, card_rows


def cached_view(data, requested, config, now):
    dates = sorted(set(date.fromisoformat(value) for value in requested))
    if not dates or len(dates) > 21 or any(abs((day - now.date()).days) > 28 for day in dates):
        raise ValueError("Requested view is outside the supported date range")
    meta = data.get("meta", {})
    structured = meta.get("source_interface") == "get_schedule"
    known = set(data.get("view_loaded_days", [])) if structured else {
        datetime.strptime(value, "%Y%m%d").date().isoformat() for value in meta.get("days", [])
    }
    if structured:
        stamp = datetime.fromisoformat(meta["fetched_at"]) if meta.get("fetched_at") else None
        if (meta.get("source_status") != "ok" or not stamp or stamp.tzinfo is None
                or not -60 <= (now - stamp).total_seconds() < 75 * 60):
            known.clear()
    elif meta.get("no_plan"):
        known.clear()
    keys = {field.name for field in fields(Lesson)}
    lessons = [Lesson(**{key: value for key, value in item.items() if key in keys})
               for item in data.get("lessons", []) if item.get("date") in known]
    weeks = {}
    for monday in sorted({day - timedelta(days=day.weekday()) for day in dates}):
        if structured:
            _, rows = card_rows(lessons, monday, show_room=config.get("show_room", True),
                                show_teacher=config.get("show_teacher", False))
        else:
            # Legacy providers only guarantee the selected sensor week.
            rows = data.get("rows_table", []) if meta.get("week_start") == monday.strftime("%Y%m%d") else []
        weeks[monday.isoformat()] = rows
    return {"weeks": weeks, "loaded_days": sorted(known & {d.isoformat() for d in dates}),
            "requested_days": [d.isoformat() for d in dates]}


def register_view_service(hass):
    import voluptuous as vol
    from homeassistant.auth.permissions.const import POLICY_READ
    from homeassistant.core import SupportsResponse
    from homeassistant.exceptions import ServiceValidationError, Unauthorized
    from homeassistant.helpers import config_validation as cv, entity_registry as er
    from homeassistant.util import dt as dt_util
    from .const import DOMAIN

    async def handle(call):
        entity_id = call.data["entity_id"]
        if call.context.user_id:
            user = await hass.auth.async_get_user(call.context.user_id)
            if not user or not user.permissions.check_entity(entity_id, POLICY_READ):
                raise Unauthorized(entity_id=entity_id, permission=POLICY_READ)
        record = er.async_get(hass).async_get(entity_id)
        if (not record or record.platform != DOMAIN or record.domain != "sensor"
                or not record.unique_id.endswith("_woche")):
            raise ServiceValidationError("Select a Suite week sensor")
        coordinator = hass.data.get(DOMAIN, {}).get(record.config_entry_id)
        if not coordinator or not coordinator.last_update_success or not coordinator.data:
            raise ServiceValidationError("Timetable data is not available")
        try:
            return cached_view(coordinator.data, call.data["dates"],
                               {**coordinator.entry.data, **coordinator.entry.options}, dt_util.now())
        except (ValueError, TypeError, KeyError) as err:
            raise ServiceValidationError("Invalid timetable view") from err

    if not hass.services.has_service(DOMAIN, "get_view"):
        hass.services.async_register(DOMAIN, "get_view", handle,
            schema=vol.Schema({vol.Required("entity_id"): cv.entity_id,
                               vol.Required("dates"): vol.All([str], vol.Length(min=1, max=21))}),
            supports_response=SupportsResponse.ONLY)
