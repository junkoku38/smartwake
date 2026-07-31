"""Intégration SmartWAKE — point d'entrée."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv, device_registry as dr, entity_registry as er

from .const import (
    DOMAIN,
    PLATFORMS,
    SERVICE_DECLENCHER,
    SERVICE_RESET,
    SERVICE_SKIP,
    SERVICE_SNOOZE,
    SERVICE_STOP,
    SERVICE_BILAN_HEBDO,
)
from .coordinator import ReveilCoordinator

_LOGGER = logging.getLogger(__name__)

SERVICE_SCHEMA = vol.Schema({vol.Required(ATTR_ENTITY_ID): vol.All(cv.ensure_list, [str])})


def _get_coordinator(hass: HomeAssistant, entity_id: str) -> ReveilCoordinator | None:
    """Trouve le coordinator à partir d'une entity_id (match strict).

    Cherche le coordinator dont l'entity_id du switch correspond exactement.
    Évite les collisions de sous-chaîne entre réveils aux noms similaires.
    """
    registry = er.async_get(hass)
    entry = registry.async_get(entity_id)
    if entry is None:
        return None
    return hass.data.get(DOMAIN, {}).get(entry.config_entry_id)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Enregistre les services du domaine."""

    async def _handle_declencher(call: ServiceCall) -> None:
        for eid in call.data.get(ATTR_ENTITY_ID, []):
            coord = _get_coordinator(hass, eid)
            if coord:
                await coord.declencher_manuel()

    async def _handle_snooze(call: ServiceCall) -> None:
        for eid in call.data.get(ATTR_ENTITY_ID, []):
            coord = _get_coordinator(hass, eid)
            if coord:
                await coord.snooze()

    async def _handle_stop(call: ServiceCall) -> None:
        for eid in call.data.get(ATTR_ENTITY_ID, []):
            coord = _get_coordinator(hass, eid)
            if coord:
                await coord.stop()

    async def _handle_skip(call: ServiceCall) -> None:
        for eid in call.data.get(ATTR_ENTITY_ID, []):
            coord = _get_coordinator(hass, eid)
            if coord:
                await coord.sauter_prochain()

    async def _handle_reset(call: ServiceCall) -> None:
        for eid in call.data.get(ATTR_ENTITY_ID, []):
            coord = _get_coordinator(hass, eid)
            if coord:
                await coord.reset()

    async def _handle_bilan_hebdo(call: ServiceCall) -> None:
        for eid in call.data.get(ATTR_ENTITY_ID, []):
            coord = _get_coordinator(hass, eid)
            if coord:
                await coord.bilan_hebdo_ia()

    hass.services.async_register(DOMAIN, SERVICE_DECLENCHER, _handle_declencher, schema=SERVICE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SNOOZE, _handle_snooze, schema=SERVICE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_STOP, _handle_stop, schema=SERVICE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SKIP, _handle_skip, schema=SERVICE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_RESET, _handle_reset, schema=SERVICE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_BILAN_HEBDO, _handle_bilan_hebdo, schema=SERVICE_SCHEMA)

    # Enregistrer les tools Assist (LLM Tool Calling) — non bloquant
    try:
        from .assist import async_setup_assist_tools
        await async_setup_assist_tools(hass)
    except Exception as exc:
        _LOGGER.debug("Assist tools non disponibles: %s", exc)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Configure une instance de réveil."""
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer="SmartWAKE",
        model="Progressive alarm",
        sw_version="2.0.0",
    )

    coordinator = ReveilCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    _LOGGER.info("SmartWAKE '%s' configuré", entry.title)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Décharge une instance de réveil."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    _LOGGER.info("SmartWAKE '%s' supprimé", entry.title)


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Recharge l'entrée après une modification via le menu d'options.

    Les écritures provoquées par une entité (heure, jours, curseurs, mode
    vacances) ne doivent pas déclencher de rechargement : le coordinator les
    applique déjà lui-même. Recharger reviendrait à recréer le coordinator,
    donc à repasser `actif` à False et à désarmer le réveil.
    """
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if coordinator is not None and coordinator.consume_internal_update():
        return
    await hass.config_entries.async_reload(entry.entry_id)