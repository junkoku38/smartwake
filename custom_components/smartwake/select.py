"""Platform select — choix des jours de réveil et du mode d'heure."""

from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from homeassistant.exceptions import HomeAssistantError

from .const import CONF_JOURS, CONF_JOURS_PERSO, CONF_MODE_HEURE, DOMAIN, JOURS_OPTIONS
from .coordinator import ReveilCoordinator
from .entity import make_device_info

_LOGGER = logging.getLogger(__name__)

SELECT_DESC = SelectEntityDescription(
    key="jours",
    name="Jours",
    icon="mdi:calendar-week",
)

MODE_HEURE_DESC = SelectEntityDescription(
    key="mode_heure",
    name="Mode heure",
    icon="mdi:clock-edit",
)

# Doit rester aligné sur _calculer_prochain() du coordinator
MODE_HEURE_OPTIONS = ["unique", "par_jour"]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: ReveilCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        ReveilSelect(coordinator, entry, SELECT_DESC),
        ReveilModeHeureSelect(coordinator, entry, MODE_HEURE_DESC),
    ])


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
        if option not in JOURS_OPTIONS:
            return
        # « Personnalisé » suppose une liste de jours, que seul le menu
        # d'options permet de saisir. L'accepter sans cette liste désactivait
        # silencieusement le réveil : plus aucun jour actif, donc plus de
        # prochain déclenchement.
        if option == "personnalise" and not self.coordinator.config.get(CONF_JOURS_PERSO):
            raise HomeAssistantError(
                "Choisissez d'abord les jours dans Options → Base → Jours "
                "personnalisés : sans eux, le réveil ne sonnerait aucun jour."
            )
        await self.coordinator.set_jours(option)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.coordinator.async_add_listener(self._handle_update))

    def _handle_update(self) -> None:
        self.async_write_ha_state()


class ReveilModeHeureSelect(SelectEntity):
    """Heure unique pour tous les jours, ou une heure par jour de la semaine."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, entry, description):
        self.coordinator = coordinator
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_select_mode_heure"
        self._attr_has_entity_name = True
        self._attr_name = description.name
        self._attr_icon = description.icon
        self._attr_options = list(MODE_HEURE_OPTIONS)
        self._attr_should_poll = False
        self._attr_device_info = make_device_info(entry)

    @property
    def current_option(self) -> str | None:
        return self.coordinator.config.get(CONF_MODE_HEURE, "unique")

    async def async_select_option(self, option: str) -> None:
        if option in MODE_HEURE_OPTIONS:
            await self.coordinator.set_config_value(CONF_MODE_HEURE, option)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.coordinator.async_add_listener(self._handle_update))

    def _handle_update(self) -> None:
        self.async_write_ha_state()