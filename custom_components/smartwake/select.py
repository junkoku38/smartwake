"""Platform select — choix des jours de réveil."""

from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_JOURS, DOMAIN, JOURS_OPTIONS
from .coordinator import ReveilCoordinator
from .entity import make_device_info

_LOGGER = logging.getLogger(__name__)

SELECT_DESC = SelectEntityDescription(
    key="jours",
    name="Jours",
    icon="mdi:calendar-week",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: ReveilCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ReveilSelect(coordinator, entry, SELECT_DESC)])


class ReveilSelect(SelectEntity):
    def __init__(self, coordinator, entry, description):
        self.coordinator = coordinator
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_select_jours"
        self._attr_has_entity_name = True
        self._attr_name = "Jours"
        self._attr_icon = description.icon
        self._attr_options = list(JOURS_OPTIONS.keys())
        self._attr_should_poll = False
        self._attr_device_info = make_device_info(entry)

    @property
    def current_option(self) -> str | None:
        return self.coordinator.config.get(CONF_JOURS, "semaine")

    async def async_select_option(self, option: str) -> None:
        if option in JOURS_OPTIONS:
            await self.coordinator.set_jours(option)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.coordinator.async_add_listener(self._handle_update))

    def _handle_update(self) -> None:
        self.async_write_ha_state()