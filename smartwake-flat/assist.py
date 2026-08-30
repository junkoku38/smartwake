"""Expose les fonctions SmartWAKE à Assist (LLM Tool Calling).

Permet de contrôler le réveil par commande vocale naturelle :
  « Réveille-moi à 6h45 demain »
  « Pas de réveil demain »
  « Active le réveil semaine »
  « Combien de temps avant le prochain réveil ? »

L'API attendue par Home Assistant est une sous-classe de `llm.API` enregistrée
via `llm.async_register_api`. La version précédente appelait
`llm.async_register_tool`, qui n'existe pas : l'AttributeError était capturée et
journalisée en debug, si bien que les quatre outils n'ont jamais été exposés.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm
from homeassistant.util.json import JsonObjectType

from .const import DOMAIN, slugify
from .coordinator import ReveilCoordinator

_LOGGER = logging.getLogger(__name__)

API_ID = f"{DOMAIN}_api"

API_PROMPT = (
    "Tu peux piloter les réveils SmartWAKE de la maison : régler leur heure, "
    "les activer ou les désactiver, sauter la prochaine occurrence et consulter "
    "leur état. Chaque réveil porte un nom ; s'il n'y en a qu'un, son nom peut "
    "être omis."
)


def _reveils(hass: HomeAssistant) -> list[ReveilCoordinator]:
    return list(hass.data.get(DOMAIN, {}).values())


def _find_coordinator(hass: HomeAssistant, name: str | None) -> ReveilCoordinator | None:
    """Trouve un coordinator par nom de réveil.

    Le nom est facultatif s'il n'existe qu'un seul réveil : l'utilisateur dit
    rarement « règle le réveil Réveil à 7 h ».
    """
    coords = _reveils(hass)
    if not name:
        return coords[0] if len(coords) == 1 else None
    cible = slugify(name)
    for coord in coords:
        if slugify(coord.entry.title) == cible:
            return coord
    # Correspondance partielle, tolérante à la reconnaissance vocale
    for coord in coords:
        if cible in slugify(coord.entry.title):
            return coord
    return None


def _erreur_introuvable(hass: HomeAssistant, name: str | None) -> JsonObjectType:
    dispo = [c.entry.title for c in _reveils(hass)]
    if not dispo:
        return {"error": "Aucun réveil SmartWAKE n'est configuré."}
    return {
        "error": f"Réveil '{name}' introuvable.",
        "reveils_disponibles": dispo,
    }


class _ReveilTool(llm.Tool):
    """Base commune : résolution du réveil visé."""

    def _coord(self, hass: HomeAssistant, args: dict[str, Any]):
        return _find_coordinator(hass, args.get("name"))


class SmartWAKESetTimeTool(_ReveilTool):
    """Règle l'heure du réveil."""

    name = "smartwake_set_time"
    description = (
        "Règle l'heure d'un réveil SmartWAKE. L'heure doit être au format HH:MM."
    )
    parameters = vol.Schema(
        {
            vol.Required("heure"): str,
            vol.Optional("name"): str,
        }
    )

    async def async_call(
        self, hass: HomeAssistant, tool_input: llm.ToolInput, llm_context: llm.LLMContext
    ) -> JsonObjectType:
        args = tool_input.tool_args
        heure = str(args.get("heure", ""))
        m = re.match(r"^(\d{1,2}):(\d{2})$", heure)
        if not m or not (0 <= int(m.group(1)) < 24 and 0 <= int(m.group(2)) < 60):
            return {"error": f"Heure invalide : {heure}. Format attendu HH:MM."}
        heure = f"{int(m.group(1)):02d}:{m.group(2)}"

        coord = self._coord(hass, args)
        if coord is None:
            return _erreur_introuvable(hass, args.get("name"))
        if not coord.actif:
            await coord.set_actif(True)
        await coord.set_heure(heure)
        return {"success": True, "name": coord.entry.title, "heure": heure}


class SmartWAKEActivateTool(_ReveilTool):
    """Active ou désactive un réveil."""

    name = "smartwake_activate"
    description = "Active ou désactive un réveil SmartWAKE."
    parameters = vol.Schema(
        {
            vol.Required("actif"): bool,
            vol.Optional("name"): str,
        }
    )

    async def async_call(
        self, hass: HomeAssistant, tool_input: llm.ToolInput, llm_context: llm.LLMContext
    ) -> JsonObjectType:
        args = tool_input.tool_args
        coord = self._coord(hass, args)
        if coord is None:
            return _erreur_introuvable(hass, args.get("name"))
        actif = bool(args.get("actif", True))
        await coord.set_actif(actif)
        return {"success": True, "name": coord.entry.title, "actif": actif}


class SmartWAKESkipTool(_ReveilTool):
    """Saute la prochaine occurrence."""

    name = "smartwake_skip"
    description = (
        "Saute la prochaine occurrence d'un réveil SmartWAKE, une seule fois. "
        "Les réveils suivants ne sont pas affectés."
    )
    parameters = vol.Schema({vol.Optional("name"): str})

    async def async_call(
        self, hass: HomeAssistant, tool_input: llm.ToolInput, llm_context: llm.LLMContext
    ) -> JsonObjectType:
        args = tool_input.tool_args
        coord = self._coord(hass, args)
        if coord is None:
            return _erreur_introuvable(hass, args.get("name"))
        await coord.sauter_prochain()
        return {"success": True, "name": coord.entry.title, "skipped": True}


class SmartWAKEStatusTool(_ReveilTool):
    """Retourne le statut d'un réveil."""

    name = "smartwake_status"
    description = (
        "Retourne l'état et l'heure du prochain déclenchement d'un réveil "
        "SmartWAKE. Sans nom, retourne l'état de tous les réveils."
    )
    parameters = vol.Schema({vol.Optional("name"): str})

    @staticmethod
    def _etat(coord: ReveilCoordinator) -> JsonObjectType:
        return {
            "name": coord.entry.title,
            "actif": coord.actif,
            "statut": coord.statut,
            "heure": coord.config.get("heure", "07:00"),
            "prochain": coord.prochain_reveil.isoformat() if coord.prochain_reveil else None,
            "snooze_utilises": coord.snooze_count,
            "prochain_saute": coord.skip_prochain,
        }

    async def async_call(
        self, hass: HomeAssistant, tool_input: llm.ToolInput, llm_context: llm.LLMContext
    ) -> JsonObjectType:
        args = tool_input.tool_args
        name = args.get("name")
        if not name:
            return {"reveils": [self._etat(c) for c in _reveils(hass)]}
        coord = self._coord(hass, args)
        if coord is None:
            return _erreur_introuvable(hass, name)
        return self._etat(coord)


class SmartWAKEAPI(llm.API):
    """Expose les outils SmartWAKE aux agents conversationnels."""

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(hass=hass, id=API_ID, name="SmartWAKE")

    async def async_get_api_instance(
        self, llm_context: llm.LLMContext
    ) -> llm.APIInstance:
        return llm.APIInstance(
            api=self,
            api_prompt=API_PROMPT,
            llm_context=llm_context,
            tools=[
                SmartWAKESetTimeTool(),
                SmartWAKEActivateTool(),
                SmartWAKESkipTool(),
                SmartWAKEStatusTool(),
            ],
        )


async def async_setup_assist_tools(hass: HomeAssistant) -> None:
    """Enregistre l'API SmartWAKE pour Assist.

    Sans effet si une autre instance l'a déjà enregistrée : la fonction est
    appelée depuis async_setup, donc une seule fois par démarrage, mais un
    rechargement de l'intégration ne doit pas provoquer d'erreur.
    """
    if any(api.id == API_ID for api in llm.async_get_apis(hass)):
        return
    llm.async_register_api(hass, SmartWAKEAPI(hass))
    _LOGGER.info("API Assist SmartWAKE enregistrée (4 outils)")
