"""Intégration SmartWAKE — point d'entrée."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse, callback
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
    SERVICE_TESTER_IA,
    integration_version,
    SCHEMA_VERSION,
    CONF_PRESENCE_LIT_SENSORS,
    CONF_WITHINGS_BED_1,
    CONF_WITHINGS_BED_2,
    CONF_AI_CAMERA_VERIF,
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
    async def _handle_tester_ia(call: ServiceCall) -> dict:
        """Exécute une tâche IA et renvoie son résultat."""
        tache = call.data["tache"]
        resultats = {}
        for eid in call.data.get(ATTR_ENTITY_ID, []):
            coord = _get_coordinator(hass, eid)
            if coord:
                resultats[eid] = await coord.tester_ia(tache)
            else:
                resultats[eid] = "Réveil introuvable"
        return {"resultats": resultats}

    hass.services.async_register(DOMAIN, SERVICE_BILAN_HEBDO, _handle_bilan_hebdo, schema=SERVICE_SCHEMA)
    hass.services.async_register(
        DOMAIN, SERVICE_TESTER_IA, _handle_tester_ia,
        schema=vol.Schema({
            vol.Required(ATTR_ENTITY_ID): vol.All(cv.ensure_list, [str]),
            vol.Required("tache"): vol.In(
                ["briefing", "musique", "suggestion", "bilan", "lever", "personnalisees"]
            ),
        }),
        supports_response=SupportsResponse.OPTIONAL,
    )

    # Enregistrer l'API Assist (LLM Tool Calling) — non bloquant.
    # L'échec était journalisé en debug, ce qui a masqué pendant longtemps le
    # fait que l'API utilisée n'existait pas.
    try:
        from .assist import async_setup_assist_tools
        await async_setup_assist_tools(hass)
    except Exception as exc:
        _LOGGER.warning(
            "API Assist SmartWAKE non enregistrée, le pilotage vocal sera "
            "indisponible : %s", exc,
        )

    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migre une entrée créée par une version antérieure.

    Le config flow déclare VERSION = 3 depuis la 2.5.0, contre 2 auparavant.
    Sans ce gestionnaire, Home Assistant refuse de charger toute entrée créée
    avant cette version : « Migration handler not found », et l'intégration ne
    démarre pas du tout (config_entries.py, async_migrate_helper).

    Le schéma n'a jamais perdu ni renommé de clé — les versions successives
    n'ont fait qu'en ajouter — et chaque lecture applique une valeur par
    défaut. Relever la version suffit donc, sans transformation des données.
    """
    if entry.version > SCHEMA_VERSION:
        # Entrée écrite par une version plus récente : on ne sait pas la lire
        _LOGGER.error(
            "L'entrée '%s' provient d'une version plus récente de SmartWAKE "
            "(schéma %s > %s). Mettez l'intégration à jour.",
            entry.title, entry.version, SCHEMA_VERSION,
        )
        return False

    if entry.version < SCHEMA_VERSION:
        _LOGGER.info(
            "Migration de '%s' du schéma %s vers %s",
            entry.title, entry.version, SCHEMA_VERSION,
        )
        data = {**entry.data}

        if entry.version < 4:
            # Les deux champs Withings figés deviennent une liste de capteurs de
            # présence au lit, ouverte aux radars millimétriques et aux autres
            # marques. Les valeurs déjà saisies sont reprises.
            capteurs = list(data.get(CONF_PRESENCE_LIT_SENSORS) or [])
            for ancienne in (CONF_WITHINGS_BED_1, CONF_WITHINGS_BED_2):
                valeur = data.pop(ancienne, None)
                if valeur and valeur not in capteurs:
                    capteurs.append(valeur)
            if capteurs:
                data[CONF_PRESENCE_LIT_SENSORS] = capteurs
            # La vérification du lever n'utilise plus de caméra
            data.pop(CONF_AI_CAMERA_VERIF, None)

        if entry.version < 5:
            # « Phase de sommeil » est supprimée : aucun capteur grand public
            # n'expose la phase de sommeil courante. Les intégrations publient
            # des agrégats au réveil, pas un état pendant la nuit.
            data.pop("sommeil_phase", None)
            data.pop("sommeil_fenetre_min", None)

        hass.config_entries.async_update_entry(
            entry, data=data, version=SCHEMA_VERSION, minor_version=0
        )

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
        sw_version=integration_version(),
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