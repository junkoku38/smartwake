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
        """Reproduit le contrat de Home Assistant.

        Renvoie True seulement si quelque chose a change, et n appelle les
        ecouteurs que dans ce cas. Le mock renvoyait None sans distinction, ce
        qui masquait un bug reel : une ecriture sans changement laissait armes
        des drapeaux cotes integration.
        """
        change = False
        if "data" in kw and entry.data != kw["data"]:
            entry.data = kw["data"]
            change = True
        for attr in ("version", "minor_version", "title", "options"):
            if attr in kw and getattr(entry, attr, None) != kw[attr]:
                setattr(entry, attr, kw[attr])
                change = True
        return change


class _Services:
    def __init__(self):
        self.calls = []

    async def async_call(self, domain, service, data=None, **kwargs):
        self.calls.append({
            "domain": domain, "service": service,
            "data": data or {}, "kwargs": kwargs,
        })

    def has_service(self, domain, service):
        return False


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