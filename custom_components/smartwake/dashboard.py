"""Génération et injection d'une carte Lovelace pour SmartWAKE."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.lovelace import LOVELACE_DATA
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

DASHBOARD_VIEW_TITLE = "SmartWAKE"


def _slugify(title: str) -> str:
    return title.lower().replace(" ", "_").replace("é", "e").replace("è", "e")[:20]


def _build_card(entry: ConfigEntry) -> dict[str, Any]:
    """Construit la config de la carte Lovelace pour ce réveil."""
    nom = entry.title.lower().replace(" ", "_")

    return {
        "type": "vertical-stack",
        "cards": [
            {
                "type": "entities",
                "title": f"⏰ {entry.title}",
                "show_header_toggle": False,
                "entities": [
                    {"entity": f"switch.{nom}_actif", "name": "Activé"},
                    {"entity": f"time.{nom}_heure", "name": "Heure"},
                    {"type": "divider"},
                    {"entity": f"select.{nom}_jours", "name": "Jours"},
                    {"type": "divider"},
                    {"entity": f"number.{nom}_snooze_min", "name": "Snooze (min)"},
                    {"entity": f"number.{nom}_max_snooze", "name": "Max snooze"},
                    {"entity": f"number.{nom}_pre_chauffage_min", "name": "Pré-chauffage (min)"},
                    {"entity": f"number.{nom}_aube_min", "name": "Aube (min)"},
                    {"entity": f"number.{nom}_volume_final", "name": "Volume final"},
                    {"entity": f"number.{nom}_duree_eclairage_min", "name": "Durée éclairage (min)"},
                    {"entity": f"number.{nom}_luminosite_max", "name": "Luminosité max"},
                    {"entity": f"number.{nom}_escalade_min", "name": "Escalade (min)"},
                    {"type": "divider"},
                    {"entity": f"binary_sensor.{nom}_sonne_aujourd_hui", "name": "Sonne aujourd'hui"},
                    {"entity": f"binary_sensor.{nom}_weekend", "name": "Weekend"},
                    {"entity": f"binary_sensor.{nom}_jour_ferie", "name": "Jour férié"},
                    {"entity": f"binary_sensor.{nom}_vacances_scolaires", "name": "Vacances scolaires"},
                    {"entity": f"sensor.{nom}_statut", "name": "État"},
                    {"entity": f"sensor.{nom}_prochain_reveil", "name": "Prochain réveil"},
                    {"entity": f"sensor.{nom}_snooze_count", "name": "Snooze utilisés"},
                ],
            },
            {
                "type": "horizontal-stack",
                "cards": [
                    {
                        "type": "button",
                        "name": "Snooze",
                        "icon": "mdi:alarm-snooze",
                        "tap_action": {
                            "action": "call-service",
                            "service": f"{DOMAIN}.snooze",
                            "target": {"entity_id": f"switch.{nom}_actif"},
                        },
                    },
                    {
                        "type": "button",
                        "name": "Stop",
                        "icon": "mdi:alarm-off",
                        "tap_action": {
                            "action": "call-service",
                            "service": f"{DOMAIN}.stop",
                            "target": {"entity_id": f"switch.{nom}_actif"},
                        },
                    },
                    {
                        "type": "button",
                        "name": "Skip",
                        "icon": "mdi:skip-next",
                        "tap_action": {
                            "action": "call-service",
                            "service": f"{DOMAIN}.sauter_prochain",
                            "target": {"entity_id": f"switch.{nom}_actif"},
                        },
                    },
                    {
                        "type": "button",
                        "name": "Déclencher",
                        "icon": "mdi:bell-ring",
                        "tap_action": {
                            "action": "call-service",
                            "service": f"{DOMAIN}.declencher",
                            "target": {"entity_id": f"switch.{nom}_actif"},
                        },
                    },
                    {
                        "type": "button",
                        "name": "Reset",
                        "icon": "mdi:restart",
                        "tap_action": {
                            "action": "call-service",
                            "service": f"{DOMAIN}.reset",
                            "target": {"entity_id": f"switch.{nom}_actif"},
                        },
                    },
                ],
            },
        ],
    }


def _get_default_dashboard(hass: HomeAssistant):
    """Récupère le dashboard par défaut (Overview)."""
    lovelace_data = hass.data.get(LOVELACE_DATA)
    if lovelace_data is None:
        return None
    # Le dashboard par défaut a url_path = None
    return lovelace_data.dashboards.get(None)


async def inject_dashboard(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Injecte une carte SmartWAKE dans le dashboard par défaut de HA."""
    try:
        lovelace_data = hass.data.get(LOVELACE_DATA)
        if lovelace_data is None:
            _LOGGER.warning("LOVELACE_DATA non trouvé — carte non injectée")
            return

        dashboard = lovelace_data.dashboards.get(None)
        if dashboard is None:
            _LOGGER.warning("Dashboard par défaut non trouvé — dashboards: %s", list(lovelace_data.dashboards.keys()))
            return

        _LOGGER.debug("Dashboard trouvé: %s (mode=%s)", dashboard.url_path, dashboard.mode)
        config = None
        try:
            config = await dashboard.async_load(force=True)
        except Exception:
            pass
        if not config:
            # Dashboard vierge — créer une config initiale
            config = {"views": []}
        _LOGGER.debug("Config Lovelace chargée: %d vues", len(config.get("views", [])))

        card = _build_card(entry)

        # Chercher une vue SmartWAKE existante
        existing_view = None
        for view in config.get("views", []):
            if view.get("title") == DASHBOARD_VIEW_TITLE:
                existing_view = view
                break

        if existing_view is None:
            existing_view = {
                "title": DASHBOARD_VIEW_TITLE,
                "path": _slugify(DASHBOARD_VIEW_TITLE),
                "icon": "mdi:alarm",
                "cards": [card],
            }
            config.setdefault("views", []).append(existing_view)
        else:
            cards = existing_view.get("cards", [])
            card_title = f"⏰ {entry.title}"
            already = any(
                c.get("cards", [{}])[0].get("title") == card_title
                for c in cards
            )
            if not already:
                cards.append(card)
            existing_view["cards"] = cards

        await dashboard.async_save(config)
        _LOGGER.info("Carte SmartWAKE injectée pour '%s'", entry.title)

    except Exception as exc:
        _LOGGER.warning("Impossible d'injecter la carte dashboard: %s (type: %s)", exc, type(exc).__name__)


async def remove_dashboard(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Retire la carte SmartWAKE du dashboard quand le réveil est supprimé."""
    try:
        dashboard = _get_default_dashboard(hass)
        if dashboard is None:
            return

        config = await dashboard.async_load(force=False) or {"views": []}
        card_title = f"⏰ {entry.title}"

        for view in config.get("views", []):
            if view.get("title") == DASHBOARD_VIEW_TITLE:
                cards = view.get("cards", [])
                view["cards"] = [
                    c for c in cards
                    if c.get("cards", [{}])[0].get("title") != card_title
                ]
                if not view["cards"]:
                    config["views"] = [
                        v for v in config["views"]
                        if v.get("title") != DASHBOARD_VIEW_TITLE
                    ]
                break

        await dashboard.async_save(config)
        _LOGGER.info("Carte SmartWAKE retirée pour '%s'", entry.title)

    except Exception as exc:
        _LOGGER.warning("Impossible de retirer la carte dashboard: %s", exc)