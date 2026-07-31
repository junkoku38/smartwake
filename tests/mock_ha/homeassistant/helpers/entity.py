"""Mock minimal de homeassistant.helpers.entity."""

from enum import StrEnum


class EntityCategory(StrEnum):
    CONFIG = "config"
    DIAGNOSTIC = "diagnostic"


class Entity:
    hass = None
    entity_description = None

    def async_write_ha_state(self):
        pass

    def async_on_remove(self, fn):
        pass
