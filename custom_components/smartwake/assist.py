"""Expose les fonctions SmartWAKE à Assist (LLM Tool Calling).

Permet de contrôler le réveil par commande vocale naturelle :
  « Réveille-moi à 6h45 demain »
  « Pas de réveil demain »
  « Active le réveil semaine »
  « Combien de temps avant le prochain réveil ? »
"""

from __future__ import annotations

import logging
import re
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.llm import Tool

from .const import DOMAIN, slugify
from .coordinator import ReveilCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_assist_tools(hass: HomeAssistant) -> None:
    """Enregistre les tools SmartWAKE pour Assist."""
    try:
        from homeassistant.helpers import llm as llm_helper
    except ImportError:
        _LOGGER.debug("LLM tools API non disponible (HA < 2025.x)")
        return

    class SmartWAKESetTimeTool(Tool):
        """Règle l'heure du réveil."""

        name = "smartwake_set_time"
        description = "Règle l'heure d'un réveil SmartWAKE. L'heure doit être au format HH:MM."

        parameters = {
            "name": {"type": "string", "description": "Nom du réveil (ex: Reveil, Semaine)"},
            "heure": {"type": "string", "description": "Heure au format HH:MM (ex: 06:45)"},
        }

        async def async_call(self, hass: HomeAssistant, tool_input: Any) -> Any:
            name = tool_input.tool_args.get("name", "")
            heure = tool_input.tool_args.get("heure", "")
            m = re.match(r"^(\d{1,2}):(\d{2})$", heure)
            if not m or not (0 <= int(m.group(1)) < 24 and 0 <= int(m.group(2)) < 60):
                return {"error": f"Heure invalide: {heure}"}
            coord = _find_coordinator(hass, name)
            if coord is None:
                return {"error": f"Réveil '{name}' introuvable"}
            if not coord.actif:
                await coord.set_actif(True)
            await coord.set_heure(heure)
            return {"success": True, "name": name, "heure": heure}

    class SmartWAKEActivateTool(Tool):
        """Active ou désactive un réveil."""

        name = "smartwake_activate"
        description = "Active ou désactive un réveil SmartWAKE."

        parameters = {
            "name": {"type": "string", "description": "Nom du réveil"},
            "actif": {"type": "boolean", "description": "true pour activer, false pour désactiver"},
        }

        async def async_call(self, hass: HomeAssistant, tool_input: Any) -> Any:
            name = tool_input.tool_args.get("name", "")
            actif = tool_input.tool_args.get("actif", True)
            coord = _find_coordinator(hass, name)
            if coord is None:
                return {"error": f"Réveil '{name}' introuvable"}
            await coord.set_actif(actif)
            return {"success": True, "name": name, "actif": actif}

    class SmartWAKESkipTool(Tool):
        """Saute le prochain réveil."""

        name = "smartwake_skip"
        description = "Saute le prochain réveil SmartWAKE (une seule fois)."

        parameters = {
            "name": {"type": "string", "description": "Nom du réveil"},
        }

        async def async_call(self, hass: HomeAssistant, tool_input: Any) -> Any:
            name = tool_input.tool_args.get("name", "")
            coord = _find_coordinator(hass, name)
            if coord is None:
                return {"error": f"Réveil '{name}' introuvable"}
            await coord.sauter_prochain()
            return {"success": True, "name": name, "skipped": True}

    class SmartWAKEStatusTool(Tool):
        """Retourne le statut d'un réveil."""

        name = "smartwake_status"
        description = "Retourne le statut et le prochain réveil d'un réveil SmartWAKE."

        parameters = {
            "name": {"type": "string", "description": "Nom du réveil"},
        }

        async def async_call(self, hass: HomeAssistant, tool_input: Any) -> Any:
            name = tool_input.tool_args.get("name", "")
            coord = _find_coordinator(hass, name)
            if coord is None:
                return {"error": f"Réveil '{name}' introuvable"}
            prochain = coord.prochain_reveil.isoformat() if coord.prochain_reveil else None
            return {
                "name": name,
                "actif": coord.actif,
                "statut": coord.statut,
                "heure": coord.config.get("heure", "07:00"),
                "prochain": prochain,
                "snooze_count": coord.snooze_count,
                "skip_prochain": coord.skip_prochain,
            }

    try:
        llm_helper.async_register_tool(SmartWAKESetTimeTool)
        llm_helper.async_register_tool(SmartWAKEActivateTool)
        llm_helper.async_register_tool(SmartWAKESkipTool)
        llm_helper.async_register_tool(SmartWAKEStatusTool)
        _LOGGER.info("SmartWAKE Assist tools enregistrés")
    except Exception as exc:
        _LOGGER.debug("Impossible d'enregistrer les Assist tools: %s", exc)


def _find_coordinator(hass: HomeAssistant, name: str) -> ReveilCoordinator | None:
    """Trouve un coordinator par nom de réveil."""
    for coord in hass.data.get(DOMAIN, {}).values():
        if slugify(coord.entry.title) == slugify(name):
            return coord
        if coord.entry.title.lower() == name.lower():
            return coord
    return None