"""Minimal mock of homeassistant.core for testing."""
from __future__ import annotations
from typing import Any, Callable
import asyncio


class HomeAssistant:
    def __init__(self):
        self.data = {}
        self.config_entries = _ConfigEntries()
        self.services = _Services()
        self.states = _States()
        self.loop = asyncio.new_event_loop()

    def async_create_task(self, coro):
        return asyncio.ensure_future(coro, loop=self.loop)


class _ConfigEntries:
    def __init__(self):
        self.entries = []

    async def async_forward_entry_setups(self, entry, platforms):
        pass

    async def async_unload_platforms(self, entry, platforms):
        return True

    async def async_reload(self, entry_id):
        pass

    def async_update_entry(self, entry, **kw):
        if "data" in kw:
            entry.data = kw["data"]


class _Services:
    def __init__(self):
        self.calls = []

    async def async_call(self, domain, service, data=None):
        self.calls.append({"domain": domain, "service": service, "data": data or {}})


class _States:
    def __init__(self):
        self._states = {}

    def set(self, entity_id, state, attributes=None):
        self._states[entity_id] = _State(entity_id, state, attributes or {})

    def get(self, entity_id):
        return self._states.get(entity_id)


class _State:
    def __init__(self, entity_id, state, attributes):
        self.entity_id = entity_id
        self.state = state
        self.attributes = attributes


State = _State


class ConfigEntry:
    def __init__(self, entry_id="test", title="Test", data=None):
        self.entry_id = entry_id
        self.title = title
        self.data = data or {}

    def async_on_unload(self, fn):
        pass

    def add_update_listener(self, fn):
        return lambda: None


def callback(fn):
    return fn


class ServiceCall:
    def __init__(self, entity_id=None):
        self.entity_id = entity_id