from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback

from .const import DOMAIN

CONF_SCHOOL_ID = "school_id"
CONF_TARGET = "target"          # Klasse (z. B. 05a)
CONF_SHOW_ROOM = "show_room"
CONF_SHOW_TEACHER = "show_teacher"

DEFAULT_SHOW_ROOM = True
DEFAULT_SHOW_TEACHER = False


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            school = (user_input.get(CONF_SCHOOL_ID) or "").strip()
            target = (user_input.get(CONF_TARGET) or "").strip()

            # defensive: verhindert KeyError -> 500
            if not school or not target:
                errors["base"] = "missing_required"
            else:
                await self.async_set_unique_id(f"{school}_{target}".lower())
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=target,
                    data=user_input,
                )

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

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @callback
    def async_get_options_flow(self):
        return OptionsFlowHandler


class OptionsFlowHandler(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # Optionen gehören in entry.options (nicht entry.data)
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SHOW_ROOM,
                    default=self.config_entry.options.get(CONF_SHOW_ROOM, DEFAULT_SHOW_ROOM),
                ): bool,
                vol.Optional(
                    CONF_SHOW_TEACHER,
                    default=self.config_entry.options.get(CONF_SHOW_TEACHER, DEFAULT_SHOW_TEACHER),
                ): bool,
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
