"""Minimal mock of homeassistant.helpers.update_coordinator."""
from __future__ import annotations
import asyncio
from typing import Any, Callable


class DataUpdateCoordinator:
    def __init__(self, hass, logger, name, update_interval=None):
        self.hass = hass
        self.logger = logger
        self.name = name
        self.update_interval = update_interval
        self._listeners = []
        self.data = None

    def async_add_listener(self, fn):
        self._listeners.append(fn)
        return lambda: None

    def async_set_updated_data(self, data):
        self.data = data
        for fn in self._listeners:
            fn()

    async def async_request_refresh(self):
        await self._async_update_data()

    async def async_update_data(self):
        await self._async_update_data()

    async def async_config_entry_first_refresh(self):
        await self._async_update_data()

    async def _async_update_data(self):
        return {}

    async def async_shutdown(self):
        pass


class UpdateFailed(Exception):
    pass