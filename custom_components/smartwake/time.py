"""Platform time — heure du réveil éditable."""

from __future__ import annotations

import logging
from datetime import time

from homeassistant.components.time import TimeEntity, TimeEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_HEURE, DOMAIN
from .coordinator import ReveilCoordinator
from .entity import make_device_info

_LOGGER = logging.getLogger(__name__)

TIME_DESC = TimeEntityDescription(
    key="heure",
    name="Heure",
    icon="mdi:alarm",
)


def _parse_heure(heure_str: str) -> time:
    parts = heure_str.split(":")
    return time(hour=int(parts[0]), minute=int(parts[1]))


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: ReveilCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ReveilTime(coordinator, entry, TIME_DESC)])


class ReveilTime(TimeEntity):
    def __init__(self, coordinator, entry, description):
        self.coordinator = coordinator
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_time_heure"
        self._attr_has_entity_name = True
        self._attr_name = "Heure"
        self._attr_icon = description.icon
        self._attr_should_poll = False
        self._attr_device_info = make_device_info(entry)

    @property
    def native_value(self) -> time | None:
        heure_str = self.coordinator.config.get(CONF_HEURE, "07:00")
        try:
            return _parse_heure(heure_str)
        except (ValueError, IndexError):
            return None

    async def async_set_value(self, value: time) -> None:
        await self.coordinator.set_heure(value.strftime("%H:%M"))

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.coordinator.async_add_listener(self._handle_update))

    def _handle_update(self) -> None:
        self.async_write_ha_state()