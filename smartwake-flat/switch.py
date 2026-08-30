"""Platform switch — activation du réveil, mode vacances, saut du prochain."""

from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import CONF_MODE_VACANCES, DOMAIN
from .coordinator import ReveilCoordinator
from .entity import make_device_info

_LOGGER = logging.getLogger(__name__)

SWITCH_DESC = SwitchEntityDescription(
    key="actif",
    name="Actif",
    icon="mdi:alarm",
)

VACANCES_DESC = SwitchEntityDescription(
    key="mode_vacances",
    name="Mode vacances",
    icon="mdi:beach",
)

SKIP_DESC = SwitchEntityDescription(
    key="saut_du_prochain",
    name="Saut du prochain",
    icon="mdi:skip-next",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: ReveilCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        ReveilSwitch(coordinator, entry, SWITCH_DESC),
        ReveilVacancesSwitch(coordinator, entry, VACANCES_DESC),
        ReveilSkipSwitch(coordinator, entry, SKIP_DESC),
    ])


class ReveilSwitch(SwitchEntity, RestoreEntity):
    """Interrupteur d'activation du réveil.

    L'état est restauré au redémarrage de Home Assistant : sans cela le réveil
    repassait à « off » et, surtout, aucun déclencheur n'était réarmé.
    """

    def __init__(self, coordinator, entry, description):
        self.coordinator = coordinator
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_switch_actif"
        self._attr_has_entity_name = True
        self._attr_name = "Actif"
        self._attr_icon = description.icon
        self._attr_should_poll = False
        self._attr_device_info = make_device_info(entry)

    @property
    def is_on(self) -> bool:
        return self.coordinator.actif

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.set_actif(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.set_actif(False)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Restaure l'activation et réarme les déclencheurs
        if not self.coordinator.actif:
            last = await self.async_get_last_state()
            if last is not None and last.state == "on":
                await self.coordinator.set_actif(True)
        self.async_on_remove(self.coordinator.async_add_listener(self._handle_update))

    def _handle_update(self) -> None:
        self.async_write_ha_state()


class ReveilVacancesSwitch(SwitchEntity):
    """Mode vacances : suspend le réveil sans le désactiver."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, entry, description):
        self.coordinator = coordinator
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_switch_mode_vacances"
        self._attr_has_entity_name = True
        self._attr_name = description.name
        self._attr_icon = description.icon
        self._attr_should_poll = False
        self._attr_device_info = make_device_info(entry)

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.config.get(CONF_MODE_VACANCES, False))

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.set_config_value(CONF_MODE_VACANCES, True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.set_config_value(CONF_MODE_VACANCES, False)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.coordinator.async_add_listener(self._handle_update))

    def _handle_update(self) -> None:
        self.async_write_ha_state()


class ReveilSkipSwitch(SwitchEntity, RestoreEntity):
    """Saut du prochain réveil.

    Contrairement au bouton « Sauter prochain », cet interrupteur rend l'état
    visible et permet d'annuler un saut sans passer par un reset complet.
    """

    def __init__(self, coordinator, entry, description):
        self.coordinator = coordinator
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_switch_saut_du_prochain"
        self._attr_has_entity_name = True
        self._attr_name = description.name
        self._attr_icon = description.icon
        self._attr_should_poll = False
        self._attr_device_info = make_device_info(entry)

    @property
    def is_on(self) -> bool:
        return self.coordinator.skip_prochain

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.set_skip(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.set_skip(False)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # La restauration du saut au redémarrage était dangereuse : _skip_date
        # étant perdu, le saut s'appliquait à tous les jours suivants.
        # On ne restaure plus le saut : un saut est ponctuel par nature.
        self.async_on_remove(self.coordinator.async_add_listener(self._handle_update))

    def _handle_update(self) -> None:
        self.async_write_ha_state()