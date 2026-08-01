"""Minimal mock of homeassistant.config_entries."""
from __future__ import annotations
from typing import Any


class ConfigFlow:
    def __init_subclass__(cls, domain=None, **kwargs):
        super().__init_subclass__(**kwargs)
        cls._domain = domain

    async def async_set_unique_id(self, uid):
        self._unique_id = uid

    def _abort_if_unique_id_configured(self):
        pass

    def async_create_entry(self, title, data):
        return {"title": title, "data": data}

    def async_show_form(self, step_id, data_schema, errors=None, description_placeholders=None):
        return {"step_id": step_id, "schema": data_schema, "errors": errors}


class OptionsFlow:
    pass


FlowResult = dict


class ConfigEntry:
    def __init__(self, entry_id="test", title="Test", data=None):
        self.entry_id = entry_id
        self.title = title
        self.data = data or {}
        self.version = 6
        self.minor_version = 0
        self.source = "user"

    def async_on_unload(self, fn):
        pass

    def add_update_listener(self, fn):
        return lambda: None