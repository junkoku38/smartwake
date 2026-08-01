"""Platform sensor — statut, prochain réveil, snooze, stats."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN, STATUT_INACTIF
from .coordinator import ReveilCoordinator
from .entity import make_device_info

_LOGGER = logging.getLogger(__name__)

# ── Sensors principaux ────────────────────────────────────────
SENSOR_STATUT = SensorEntityDescription(
    key="statut", name="Statut", icon="mdi:alarm-check",
    device_class="enum",
    options=["idle", "prewake", "ringing", "snoozed", "done", "inactif"],
)
SENSOR_PROCHAIN = SensorEntityDescription(
    key="prochain", name="Prochain réveil", icon="mdi:calendar-clock",
)
SENSOR_FIN_SNOOZE = SensorEntityDescription(
    key="fin_snooze", name="Fin du snooze", icon="mdi:alarm-snooze",
)
SENSOR_SNOOZE = SensorEntityDescription(
    key="snooze_count", name="Snooze utilisés", icon="mdi:restart",
    entity_category=EntityCategory.DIAGNOSTIC, state_class=SensorStateClass.MEASUREMENT,
)

# ── Sensors de statistiques (persistants) ────────────────────
SENSOR_TOTAL_DECLENCHEMENTS = SensorEntityDescription(
    key="total_declenchements", name="Déclenchements (total)", icon="mdi:bell-ring-outline",
    entity_category=EntityCategory.DIAGNOSTIC, state_class=SensorStateClass.TOTAL_INCREASING,
)
SENSOR_TOTAL_SNOOZES = SensorEntityDescription(
    key="total_snoozes", name="Snoozes (total)", icon="mdi:alarm-snooze",
    entity_category=EntityCategory.DIAGNOSTIC, state_class=SensorStateClass.TOTAL_INCREASING,
)
SENSOR_TOTAL_STOPS = SensorEntityDescription(
    key="total_stops", name="Stops (total)", icon="mdi:alarm-off",
    entity_category=EntityCategory.DIAGNOSTIC, state_class=SensorStateClass.TOTAL_INCREASING,
)
SENSOR_DERNIER_REVEIL = SensorEntityDescription(
    key="dernier_reveil", name="Dernier réveil", icon="mdi:history",
    entity_category=EntityCategory.DIAGNOSTIC,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: ReveilCoordinator = hass.data[DOMAIN][entry.entry_id]
    if not hasattr(coordinator, "_stats") or coordinator._stats is None:
        coordinator._stats = {
            "total_declenchements": 0, "total_snoozes": 0, "total_stops": 0,
            "dernier_reveil": None,
        }
    async_add_entities([
        ReveilStatutSensor(coordinator, entry, SENSOR_STATUT),
        ReveilProchainSensor(coordinator, entry, SENSOR_PROCHAIN),
        ReveilSnoozeSensor(coordinator, entry, SENSOR_SNOOZE),
        ReveilFinSnoozeSensor(coordinator, entry, SENSOR_FIN_SNOOZE),
        StatsSensor(coordinator, entry, SENSOR_TOTAL_DECLENCHEMENTS),
        StatsSensor(coordinator, entry, SENSOR_TOTAL_SNOOZES),
        StatsSensor(coordinator, entry, SENSOR_TOTAL_STOPS),
        StatsSensor(coordinator, entry, SENSOR_DERNIER_REVEIL),
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


class ReveilFinSnoozeSensor(_BaseSensor):
    """Instant de reprise de la sonnerie, pour un compte à rebours réel."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._attr_device_class = "timestamp"

    @property
    def native_value(self) -> datetime | None:
        return self.coordinator.snooze_fin


class ReveilSnoozeSensor(_BaseSensor):
    @property
    def native_value(self) -> int:
        return self.coordinator.snooze_count


class StatsSensor(RestoreEntity, _BaseSensor):
    """Sensor de statistiques persistant (restauré au redémarrage)."""

    @property
    def native_value(self) -> Any:
        stats = getattr(self.coordinator, "_stats", {})
        key = self.entity_description.key
        if key == "dernier_reveil":
            return stats.get(key)
        return stats.get(key, 0)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last_state := await self.async_get_last_state()) is not None:
            stats = getattr(self.coordinator, "_stats", {})
            key = self.entity_description.key
            try:
                if key == "dernier_reveil":
                    stats[key] = last_state.state
                else:
                    stats[key] = int(float(last_state.state))
            except (ValueError, TypeError):
                pass