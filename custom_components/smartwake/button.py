"""Platform button — boutons d'action (stop, skip, reset, declencher)."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import ReveilCoordinator
from .entity import make_device_info

_LOGGER = logging.getLogger(__name__)

BTN_STOP = ButtonEntityDescription(key="stop", name="Stop", icon="mdi:stop")
BTN_SKIP = ButtonEntityDescription(key="skip", name="Sauter prochain", icon="mdi:skip-next")
BTN_RESET = ButtonEntityDescription(key="reset", name="Reset", icon="mdi:restart")
BTN_DECLENCHER = ButtonEntityDescription(key="declencher", name="Déclencher", icon="mdi:alarm")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: ReveilCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        ReveilButton(coordinator, entry, BTN_STOP, "stop"),
        ReveilButton(coordinator, entry, BTN_SKIP, "sauter_prochain"),
        ReveilButton(coordinator, entry, BTN_RESET, "reset"),
        ReveilButton(coordinator, entry, BTN_DECLENCHER, "declencher_manuel"),
    ])


class ReveilButton(ButtonEntity):
    def __init__(self, coordinator, entry, description, action_name):
        self.coordinator = coordinator
        self.entity_description = description
        self._action_name = action_name
        self._attr_unique_id = f"{entry.entry_id}_button_{description.key}"
        self._attr_has_entity_name = True
        self._attr_name = description.name
        self._attr_icon = description.icon
        self._attr_should_poll = False
        self._attr_device_info = make_device_info(entry)

    async def async_press(self) -> None:
        await getattr(self.coordinator, self._action_name)()