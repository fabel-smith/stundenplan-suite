from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import DOMAIN
from .schulmanager_schedule import course_options, read_schedules

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


class ScheduleFlowMixin:
    """Explicit child/account selection, followed by optional course exclusions."""

    async def async_step_schedule_child(self, user_input=None):
        errors = {}
        if not hasattr(self, "_schedule_students"):
            try:
                self._schedule_students = await read_schedules(self.hass)
            except Exception:
                return self.async_abort(reason="schedule_unavailable")
        choices = {f"{s['config_entry_id']}:{s['student_id']}": s for s in self._schedule_students}
        if not choices:
            return self.async_abort(reason="schedule_unavailable")
        if user_input is not None:
            selected = choices.get(user_input.get("student"))
            if selected is None:
                errors["base"] = "invalid_student"
            else:
                self._schedule_student = selected
                same = (self._schedule_pending.get("schedule_entry_id") == selected["config_entry_id"]
                        and self._schedule_pending.get("schedule_student_id") == selected["student_id"])
                if not same:
                    self._schedule_pending["excluded_course_ids"] = []
                self._schedule_pending.update(
                    use_schedule_service=True, schedule_entry_id=selected["config_entry_id"],
                    schedule_student_id=selected["student_id"])
                return await self.async_step_schedule_courses()
        current = f"{self._schedule_pending.get('schedule_entry_id')}:{self._schedule_pending.get('schedule_student_id')}"
        marker = vol.Required("student", **({"default": current} if current in choices else {}))
        schema = vol.Schema({marker: selector.SelectSelector(selector.SelectSelectorConfig(
            options=[{"value": key, "label": f"{s.get('name') or s['student_id']} / {s.get('school') or 'Schulmanager'} (Konto {s['config_entry_id'][-6:]})"}
                     for key, s in choices.items()], mode=selector.SelectSelectorMode.DROPDOWN))})
        return self.async_show_form(step_id="schedule_child", data_schema=schema, errors=errors)

    async def async_step_schedule_courses(self, user_input=None):
        saved = self._schedule_pending.get("excluded_course_ids", [])
        choices = course_options(self._schedule_student, saved)
        errors = {}
        if user_input is not None:
            values = user_input.get("excluded_course_ids", [])
            if not set(values) <= {c["value"] for c in choices}:
                errors["base"] = "invalid_courses"
            else:
                self._schedule_pending["excluded_course_ids"] = values
                return await self._finish_schedule()
        schema = vol.Schema({vol.Optional("excluded_course_ids", default=saved):
            selector.SelectSelector(selector.SelectSelectorConfig(
                options=choices, multiple=True, mode=selector.SelectSelectorMode.LIST))})
        return self.async_show_form(step_id="schedule_courses", data_schema=schema, errors=errors)


class Stundenplan24WeekConfigFlow(ScheduleFlowMixin, config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        return self.async_show_menu(step_id="user", menu_options=["stundenplan24", "schulmanager_schedule", "schulmanager"])

    async def async_step_schulmanager_schedule(self, user_input=None):
        errors = {}
        if user_input is not None:
            target = user_input.get("target", "").strip()
            if not target:
                errors["base"] = "missing_required"
            elif any(e.data.get("target", "").casefold() == target.casefold()
                     for e in self.hass.config_entries.async_entries(DOMAIN)):
                errors["base"] = "target_in_use"
            else:
                self._schedule_pending = {**user_input, "target": target, "provider": "schulmanager"}
                return await self.async_step_schedule_child()
        return self.async_show_form(step_id="schulmanager_schedule", errors=errors,
            data_schema=vol.Schema({vol.Required("target"): str,
                vol.Optional(CONF_SHOW_ROOM, default=True): bool,
                vol.Optional(CONF_SHOW_TEACHER, default=False): bool}))

    async def _finish_schedule(self):
        data = self._schedule_pending
        await self.async_set_unique_id(f"schulmanager_{data['schedule_entry_id']}_{data['schedule_student_id']}")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=data["target"], data=data)

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



class OptionsFlowHandler(ScheduleFlowMixin, config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        # NICHT self.config_entry setzen (read-only / kein setter)
        self._entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            if self._entry.data.get("provider") == "schulmanager" and user_input.get("use_schedule_service"):
                self._schedule_pending = {**self._entry.options, **user_input}
                for key in ("schedule_entry_id", "schedule_student_id", "excluded_course_ids"):
                    if key not in self._schedule_pending and key in self._entry.data:
                        self._schedule_pending[key] = self._entry.data[key]
                return await self.async_step_schedule_child()
            if self._entry.data.get("provider") == "schulmanager":
                self._legacy_pending = {**self._entry.options, **user_input, "use_schedule_service": False}
                return await self.async_step_legacy_sources()
            return self.async_create_entry(title="", data=user_input)

        options = self._entry.options or {}

        if self._entry.data.get("provider") == "schulmanager":
            fields = {
                vol.Optional("use_schedule_service", default=options.get("use_schedule_service", self._entry.data.get("use_schedule_service", False))): bool,
                vol.Optional(CONF_UPDATE_MINUTES, default=options.get(CONF_UPDATE_MINUTES, 5)): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
                vol.Optional(CONF_SHOW_ROOM, default=options.get(CONF_SHOW_ROOM, self._entry.data.get(CONF_SHOW_ROOM, True))): bool,
                vol.Optional(CONF_SHOW_TEACHER, default=options.get(CONF_SHOW_TEACHER, self._entry.data.get(CONF_SHOW_TEACHER, False))): bool,
            }
            return self.async_show_form(step_id="schulmanager_options", data_schema=vol.Schema(fields))

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

    async def _finish_schedule(self):
        return self.async_create_entry(title="", data=self._schedule_pending)

    async def async_step_schulmanager_options(self, user_input=None):
        return await self.async_step_init(user_input)

    async def async_step_legacy_sources(self, user_input=None):
        config = {**self._entry.data, **self._legacy_pending}
        errors = {}
        required = ("calendar_entity", "today_entity", "tomorrow_entity", "week_entity")
        if user_input is not None:
            if any(not user_input.get(key) for key in required):
                errors["base"] = "legacy_sources_required"
                config.update(user_input)
            else:
                # An omitted optional selector explicitly clears a previous selection.
                self._legacy_pending.update(user_input)
                self._legacy_pending["changes_entity"] = user_input.get("changes_entity", "")
                return self.async_create_entry(title="", data=self._legacy_pending)
        fields = {}
        for key in (*required, "changes_entity"):
            value = config.get(key)
            marker_type = vol.Required if key in required else vol.Optional
            marker = marker_type(key, **({"default": value} if value else {}))
            fields[marker] = selector.EntitySelector(selector.EntitySelectorConfig(
                domain="calendar" if key == "calendar_entity" else "sensor", integration="schulmanager"))
        return self.async_show_form(step_id="legacy_sources", data_schema=vol.Schema(fields), errors=errors)
