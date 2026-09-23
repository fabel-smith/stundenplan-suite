from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import DOMAIN

CONF_SCHOOL_ID = "school_id"
CONF_TARGET = "target"
CONF_SHOW_ROOM = "show_room"
CONF_SHOW_TEACHER = "show_teacher"

CONF_UPDATE_MINUTES = "update_minutes"
CONF_WPLAN_ENABLED = "wplan_enabled"
CONF_WPLAN_DAYS = "wplan_days"

DEFAULT_SHOW_ROOM = True
DEFAULT_SHOW_TEACHER = False
DEFAULT_UPDATE_MINUTES = 360
DEFAULT_WPLAN_ENABLED = False
DEFAULT_WPLAN_DAYS = 3


class Stundenplan24WeekConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        return self.async_show_menu(step_id="user", menu_options=["stundenplan24", "schulmanager"])

    async def async_step_schulmanager(self, user_input=None):
        errors = {}
        if user_input is not None:
            user_input["target"] = user_input.get("target", "").strip()
            if not user_input["target"]:
                errors["base"] = "missing_required"
            elif any(e.data.get("target", "").casefold() == user_input["target"].casefold()
                     for e in self.hass.config_entries.async_entries(DOMAIN)):
                errors["base"] = "target_in_use"
            else:
                await self.async_set_unique_id("schulmanager_" + user_input["calendar_entity"])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=user_input["target"],
                                              data={**user_input, "provider": "schulmanager"})
        schema = vol.Schema({
            vol.Required("target"): str,
            vol.Required("calendar_entity"): selector.EntitySelector(selector.EntitySelectorConfig(domain="calendar", integration="schulmanager")),
            vol.Required("today_entity"): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", integration="schulmanager")),
            vol.Required("tomorrow_entity"): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", integration="schulmanager")),
            vol.Required("week_entity"): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", integration="schulmanager")),
            vol.Optional("changes_entity"): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", integration="schulmanager")),
            vol.Optional(CONF_SHOW_ROOM, default=True): bool,
            vol.Optional(CONF_SHOW_TEACHER, default=False): bool,
        })
        return self.async_show_form(step_id="schulmanager", data_schema=schema, errors=errors)

    async def async_step_stundenplan24(self, user_input=None):
        errors = {}

        if user_input is not None:
            school = (user_input.get(CONF_SCHOOL_ID) or "").strip()
            target = (user_input.get(CONF_TARGET) or "").strip()

            if not school or not target:
                errors["base"] = "missing_required"
            else:
                await self.async_set_unique_id(f"{school}_{target}".lower())
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=target, data=user_input)

        schema = vol.Schema(
            {
                vol.Required(CONF_SCHOOL_ID): str,
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Required(CONF_TARGET): str,
                vol.Optional(CONF_SHOW_ROOM, default=DEFAULT_SHOW_ROOM): bool,
                vol.Optional(CONF_SHOW_TEACHER, default=DEFAULT_SHOW_TEACHER): bool,
            }
        )

        return self.async_show_form(step_id="stundenplan24", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return OptionsFlowHandler(config_entry)



class OptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        # NICHT self.config_entry setzen (read-only / kein setter)
        self._entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self._entry.options or {}

        if self._entry.data.get("provider") == "schulmanager":
            fields = {
                vol.Optional(CONF_UPDATE_MINUTES, default=options.get(CONF_UPDATE_MINUTES, 5)): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
                vol.Optional(CONF_SHOW_ROOM, default=options.get(CONF_SHOW_ROOM, self._entry.data.get(CONF_SHOW_ROOM, True))): bool,
                vol.Optional(CONF_SHOW_TEACHER, default=options.get(CONF_SHOW_TEACHER, self._entry.data.get(CONF_SHOW_TEACHER, False))): bool,
            }
            for key in ("calendar_entity", "today_entity", "tomorrow_entity", "week_entity", "changes_entity"):
                value = options.get(key, self._entry.data.get(key))
                marker = vol.Required(key, default=value) if key != "changes_entity" else vol.Optional(key, **({"default": value} if value else {}))
                fields[marker] = selector.EntitySelector(selector.EntitySelectorConfig(domain="calendar" if key == "calendar_entity" else "sensor", integration="schulmanager"))
            return self.async_show_form(step_id="init", data_schema=vol.Schema(fields))

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SHOW_ROOM,
                    default=options.get(CONF_SHOW_ROOM, DEFAULT_SHOW_ROOM),
                ): bool,
                vol.Optional(
                    CONF_SHOW_TEACHER,
                    default=options.get(CONF_SHOW_TEACHER, DEFAULT_SHOW_TEACHER),
                ): bool,
                vol.Optional(
                    CONF_UPDATE_MINUTES,
                    default=int(options.get(CONF_UPDATE_MINUTES, DEFAULT_UPDATE_MINUTES)),
                ): vol.All(vol.Coerce(int), vol.Range(min=5, max=1440)),
                vol.Optional(
                    CONF_WPLAN_ENABLED,
                    default=bool(options.get(CONF_WPLAN_ENABLED, DEFAULT_WPLAN_ENABLED)),
                ): bool,
                vol.Optional(
                    CONF_WPLAN_DAYS,
                    default=int(options.get(CONF_WPLAN_DAYS, DEFAULT_WPLAN_DAYS)),
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=14)),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
