"""Platform binary_sensor — sonne aujourd'hui, en cours, jour férié, weekend, vacances sco.

Toutes ces sondes sont des entités HA supervisables (History, Logbook, Lovelace, Alertes).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_change

from .const import (
    CONF_IGNORER_FERIES,
    CONF_IGNORER_VACANCES_SCOLAIRE,
    CONF_VACANCES_SCOLAIRES_CALENDAR,
    CONF_WORKDAY_SENSOR,
    DOMAIN,
    STATUT_PREWAKE,
    STATUT_RINGING,
    STATUT_SNOOZED,
)
from .coordinator import ReveilCoordinator
from .entity import make_device_info

_LOGGER = logging.getLogger(__name__)

BS_SONNE = BinarySensorEntityDescription(
    key="sonne_aujourd_hui", name="Sonne aujourd'hui", icon="mdi:calendar-alert"
)
BS_EN_COURS = BinarySensorEntityDescription(
    key="en_cours", name="Réveil en cours", icon="mdi:alarm-bell"
)
BS_FERIE = BinarySensorEntityDescription(
    key="jour_ferie", name="Jour férié", icon="mdi:calendar-remove"
)
BS_WEEKEND = BinarySensorEntityDescription(
    key="weekend", name="Weekend", icon="mdi:calendar-weekend"
)
BS_VACANCES_SCO = BinarySensorEntityDescription(
    key="vacances_scolaires", name="Vacances scolaires", icon="mdi:school"
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: ReveilCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        ReveilSonneAujourdhui(coordinator, entry, BS_SONNE),
        ReveilEnCours(coordinator, entry, BS_EN_COURS),
        ReveilFerie(coordinator, entry, BS_FERIE),
        ReveilWeekend(coordinator, entry, BS_WEEKEND),
        ReveilVacancesSco(coordinator, entry, BS_VACANCES_SCO),
    ])


class _BaseBinary(BinarySensorEntity):
    """Base — écoute les updates du coordinator."""

    def __init__(self, coordinator, entry, description):
        self.coordinator = coordinator
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_binary_{description.key}"
        self._attr_has_entity_name = True
        self._attr_name = description.name
        self._attr_icon = description.icon
        self._attr_should_poll = False
        self._attr_device_info = make_device_info(entry)
        self._unsub_trackers = []

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.coordinator.async_add_listener(self._handle_update))
        for unsub in self._unsub_trackers:
            self.async_on_remove(unsub)

    def _handle_update(self, *args, **kwargs) -> None:
        self.async_write_ha_state()


class ReveilSonneAujourdhui(_BaseBinary):
    """Vrai si le réveil doit sonner aujourd'hui (toutes conditions combinées)."""

    @property
    def is_on(self) -> bool:
        if not self.coordinator.actif:
            return False
        return self.coordinator._sonne_aujourd_hui(datetime.now())

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Recalculer à minuit (changement de jour)
        unsub = async_track_time_change(self.hass, self._handle_update, hour=0, minute=0, second=5)
        self._unsub_trackers.append(unsub)


class ReveilEnCours(_BaseBinary):
    """Vrai si le cycle de réveil est actif (ringing, prewake, snoozed)."""

    @property
    def is_on(self) -> bool:
        return self.coordinator.statut in (STATUT_RINGING, STATUT_PREWAKE, STATUT_SNOOZED)


class ReveilFerie(_BaseBinary):
    """Jour férié — interroge le capteur workday configuré (supervisable dans History)."""

    @property
    def is_on(self) -> bool:
        cfg = self.coordinator.config
        sensor = cfg.get(CONF_WORKDAY_SENSOR)
        if not sensor:
            return False
        state = self.hass.states.get(sensor)
        if state is None:
            return False
        # workday_sensor : "off" = férié/weekend, "on" = travaillé
        # On exclut les weekends (sonde dédiée)
        if self._is_weekend():
            return False
        return state.state == "off"

    def _is_weekend(self) -> bool:
        return datetime.now().weekday() in (5, 6)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Écouter les changements du workday sensor en temps réel
        cfg = self.coordinator.config
        sensor = cfg.get(CONF_WORKDAY_SENSOR)
        if sensor:
            unsub = async_track_state_change_event(self.hass, [sensor], self._handle_update)
            self._unsub_trackers.append(unsub)
        # Recalcul à minuit
        unsub_midnight = async_track_time_change(self.hass, self._handle_update, hour=0, minute=0, second=5)
        self._unsub_trackers.append(unsub_midnight)


class ReveilWeekend(_BaseBinary):
    """Weekend = samedi (5) ou dimanche (6). Entité purement temporelle."""

    @property
    def is_on(self) -> bool:
        return datetime.now().weekday() in (5, 6)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Recalcul à minuit
        unsub = async_track_time_change(self.hass, self._handle_update, hour=0, minute=0, second=5)
        self._unsub_trackers.append(unsub)


class ReveilVacancesSco(_BaseBinary):
    """Vacances scolaires — interroge un calendar entity si configuré."""

    @property
    def is_on(self) -> bool:
        cfg = self.coordinator.config
        calendar = cfg.get(CONF_VACANCES_SCOLAIRES_CALENDAR)
        if not calendar:
            return False
        state = self.hass.states.get(calendar)
        if state is None:
            return False
        return state.state == "on"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Écouter les changements du calendar en temps réel
        cfg = self.coordinator.config
        calendar = cfg.get(CONF_VACANCES_SCOLAIRES_CALENDAR)
        if calendar:
            unsub = async_track_state_change_event(self.hass, [calendar], self._handle_update)
            self._unsub_trackers.append(unsub)
        # Recalcul à minuit
        unsub_midnight = async_track_time_change(self.hass, self._handle_update, hour=0, minute=0, second=5)
        self._unsub_trackers.append(unsub_midnight)