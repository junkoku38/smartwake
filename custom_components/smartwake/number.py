"""Platform number — valeurs numériques éditables (snooze, prechauffe, etc.)."""

from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import (
    CONF_AUBE_MIN,
    CONF_BRIGHTNESS_MAX,
    CONF_CAFETIERE_MIN,
    CONF_DUREE_PROGRESSIVE,
    CONF_ESCALADE_MIN,
    CONF_PRECHAUFFE_MIN,
    CONF_SNOOZE_DUREE,
    CONF_SNOOZE_MAX,
    CONF_VOLUME_FINAL,
    CONF_VOLUME_INITIAL,
    DEFAULT_AUBE_MIN,
    DEFAULT_BRIGHTNESS_MAX,
    DEFAULT_CAFETIERE_MIN,
    DEFAULT_DUREE_PROGRESSIVE,
    DEFAULT_ESCALADE_MIN,
    DEFAULT_PRECHAUFFE_MIN,
    DEFAULT_SNOOZE_DUREE,
    DEFAULT_SNOOZE_MAX,
    DEFAULT_VOLUME_FINAL,
    DEFAULT_VOLUME_INITIAL,
    DOMAIN,
)
from .coordinator import ReveilCoordinator
from .entity import make_device_info

_LOGGER = logging.getLogger(__name__)

NUMBERS = [
    NumberEntityDescription(
        key=CONF_SNOOZE_DUREE, name="Snooze (min)",
        icon="mdi:timer-sand", native_min_value=1, native_max_value=30, native_step=1,
    ),
    NumberEntityDescription(
        key=CONF_SNOOZE_MAX, name="Max snooze",
        icon="mdi:restart", native_min_value=0, native_max_value=5, native_step=1,
    ),
    NumberEntityDescription(
        key=CONF_PRECHAUFFE_MIN, name="Pré-chauffage (min)",
        icon="mdi:radiator", native_min_value=0, native_max_value=120, native_step=5,
    ),
    NumberEntityDescription(
        key=CONF_AUBE_MIN, name="Aube (min)",
        icon="mdi:weather-sunset-up", native_min_value=0, native_max_value=60, native_step=5,
    ),
    NumberEntityDescription(
        key=CONF_DUREE_PROGRESSIVE, name="Durée éclairage (min)",
        icon="mdi:lightbulb-on", native_min_value=5, native_max_value=60, native_step=1,
    ),
    NumberEntityDescription(
        key=CONF_BRIGHTNESS_MAX, name="Luminosité max",
        icon="mdi:brightness-5", native_min_value=1, native_max_value=255, native_step=1,
    ),
    NumberEntityDescription(
        key=CONF_ESCALADE_MIN, name="Escalade (min)",
        icon="mdi:volume-high", native_min_value=1, native_max_value=30, native_step=1,
    ),
    NumberEntityDescription(
        key=CONF_VOLUME_INITIAL, name="Volume initial",
        icon="mdi:volume-low", native_min_value=0.01, native_max_value=1, native_step=0.01,
    ),
    NumberEntityDescription(
        key=CONF_VOLUME_FINAL, name="Volume final",
        icon="mdi:volume-medium", native_min_value=0.01, native_max_value=1, native_step=0.01,
    ),
    NumberEntityDescription(
        key=CONF_CAFETIERE_MIN, name="Café avant (min)",
        icon="mdi:coffee", native_min_value=0, native_max_value=30, native_step=1,
    ),
]

DEFAULTS = {
    CONF_SNOOZE_DUREE: DEFAULT_SNOOZE_DUREE,
    CONF_SNOOZE_MAX: DEFAULT_SNOOZE_MAX,
    CONF_PRECHAUFFE_MIN: DEFAULT_PRECHAUFFE_MIN,
    CONF_AUBE_MIN: DEFAULT_AUBE_MIN,
    CONF_DUREE_PROGRESSIVE: DEFAULT_DUREE_PROGRESSIVE,
    CONF_BRIGHTNESS_MAX: DEFAULT_BRIGHTNESS_MAX,
    CONF_ESCALADE_MIN: DEFAULT_ESCALADE_MIN,
    CONF_VOLUME_INITIAL: DEFAULT_VOLUME_INITIAL,
    CONF_VOLUME_FINAL: DEFAULT_VOLUME_FINAL,
    CONF_CAFETIERE_MIN: DEFAULT_CAFETIERE_MIN,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: ReveilCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        ReveilNumber(coordinator, entry, desc) for desc in NUMBERS
    ])


class ReveilNumber(NumberEntity):
    def __init__(self, coordinator, entry, description):
        self.coordinator = coordinator
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_number_{description.key}"
        self._attr_has_entity_name = True
        self._attr_name = description.name
        self._attr_icon = description.icon
        self._attr_should_poll = False
        self._attr_mode = NumberMode.SLIDER
        self._attr_device_info = make_device_info(entry)

    @property
    def native_value(self) -> float | None:
        return self.coordinator.config.get(
            self.entity_description.key, DEFAULTS.get(self.entity_description.key, 0)
        )

    async def async_set_native_value(self, value: float) -> None:
        key = self.entity_description.key
        new_data = {**self.entry.data, key: value}
        self.hass.config_entries.async_update_entry(self.entry, data=new_data)
        if self.coordinator.actif:
            self.coordinator._planifier_trigger()
        self.coordinator._notify()

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.coordinator.async_add_listener(self._handle_update))

    def _handle_update(self) -> None:
        self.async_write_ha_state()