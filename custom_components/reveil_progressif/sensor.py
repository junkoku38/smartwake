"""Platform sensor — statut, prochain réveil, snooze count."""

from __future__ import annotations

import logging
from datetime import datetime

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, STATUT_INACTIF
from .coordinator import ReveilCoordinator
from .entity import make_device_info

_LOGGER = logging.getLogger(__name__)

SENSOR_STATUT = SensorEntityDescription(
    key="statut",
    name="Statut",
    icon="mdi:alarm-check",
)

SENSOR_PROCHAIN = SensorEntityDescription(
    key="prochain",
    name="Prochain réveil",
    icon="mdi:calendar-clock",
)

SENSOR_SNOOZE = SensorEntityDescription(
    key="snooze_count",
    name="Snooze (count)",
    icon="mdi:restart",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: ReveilCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        ReveilStatutSensor(coordinator, entry, SENSOR_STATUT),
        ReveilProchainSensor(coordinator, entry, SENSOR_PROCHAIN),
        ReveilSnoozeSensor(coordinator, entry, SENSOR_SNOOZE),
    ])


class _BaseSensor(SensorEntity):
    def __init__(self, coordinator, entry, description):
        self.coordinator = coordinator
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_sensor_{description.key}"
        self._attr_has_entity_name = True
        self._attr_name = description.name
        self._attr_icon = description.icon
        self._attr_should_poll = False
        self._attr_device_info = make_device_info(entry)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.coordinator.async_add_listener(self._handle_update))

    def _handle_update(self) -> None:
        self.async_write_ha_state()


class ReveilStatutSensor(_BaseSensor):
    @property
    def native_value(self) -> str:
        return self.coordinator.statut or STATUT_INACTIF


class ReveilProchainSensor(_BaseSensor):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._attr_device_class = "timestamp"

    @property
    def native_value(self) -> datetime | None:
        return self.coordinator.prochain_reveil


class ReveilSnoozeSensor(_BaseSensor):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._attr_state_class = "measurement"

    @property
    def native_value(self) -> int:
        return self.coordinator.snooze_count